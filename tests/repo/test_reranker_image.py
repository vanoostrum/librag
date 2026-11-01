# Copyright (C) 2026 Theo van Oostrum
"""The image carries the live reranker and its model; the `checks` job carries neither.

These tests read the Dockerfile, pyproject.toml, uv.lock and the CI workflow.
The e2e job builds the image itself.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from librag.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
RERANK_PACKAGES = {"torch", "sentence-transformers"}


def _name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9._-]+", requirement)
    assert match, requirement
    return match.group().lower()


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _dockerfile() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_reranker_packages_are_only_in_the_rerank_extra() -> None:
    """sentence-transformers and PyTorch are in the `rerank` extra, nowhere else."""
    project = _pyproject()
    extra = {_name(r) for r in project["project"]["optional-dependencies"]["rerank"]}
    assert extra == RERANK_PACKAGES
    required = {_name(r) for r in project["project"]["dependencies"]}
    groups = {
        _name(r) for group in project["dependency-groups"].values() for r in group
    }
    assert not RERANK_PACKAGES & (required | groups)


def test_torch_comes_from_the_cpu_index() -> None:
    """pyproject.toml and uv.lock take PyTorch from the CPU-only wheel index."""
    uv = _pyproject()["tool"]["uv"]
    [source] = uv["sources"]["torch"]
    [index] = [index for index in uv["index"] if index["name"] == source["index"]]
    assert index["url"] == CPU_INDEX
    assert index["explicit"] is True
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    torches = [package for package in lock["package"] if package["name"] == "torch"]
    assert torches
    for torch in torches:
        assert torch["source"] == {"registry": CPU_INDEX}, torch["version"]


def test_image_installs_the_extra_and_bakes_in_the_default_model() -> None:
    """Every `uv sync` in the Dockerfile adds the extra, and the build loads the model.

    The model is the default of LIBRAG_RERANKER_MODEL, and the hub goes offline
    after the download, so the running stack never fetches a model.
    """
    dockerfile = _dockerfile()
    syncs = re.findall(r"uv sync [^\n]*", dockerfile)
    assert syncs
    assert all("--extra rerank" in sync for sync in syncs), syncs
    assert f"ARG RERANKER_MODEL={Settings().reranker_model}\n" in dockerfile
    assert "LIBRAG_RERANKER_MODEL=${RERANKER_MODEL}" in dockerfile
    bake = dockerfile.index("CrossEncoder(sys.argv[1])")
    assert dockerfile.index("ENV HF_HUB_OFFLINE=1") > bake


def test_checks_job_does_not_install_the_extra() -> None:
    """The `checks` job syncs without extras, so it never installs PyTorch."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    runs = [step.get("run", "") for step in workflow["jobs"]["checks"]["steps"]]
    syncs = [run for run in runs if "uv sync" in run]
    assert syncs
    for sync in syncs:
        assert "--extra" not in sync
        assert "--all-extras" not in sync
