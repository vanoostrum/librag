# Copyright (C) 2026 Theo van Oostrum
"""The committed evaluation set, the eval scripts, and what git ignores.

The scripts run with a stand-in for `uv` on PATH, which logs its arguments, so
the test needs no stack and no network.
"""

import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from librag.evaluation.evalset import QUESTION_TYPES, load

ROOT = Path(__file__).resolve().parents[2]
MIN_QUESTIONS = 20
MIN_PER_TYPE = 3


def test_committed_set_covers_every_type() -> None:
    """eval/retrieval.toml loads, with 20+ questions and 3+ of each type."""
    evalset = load(ROOT / "eval" / "retrieval.toml")
    assert {book.gutenberg for book in evalset.books.values()} == {1342, 105, 84, 345}
    assert len(evalset.questions) >= MIN_QUESTIONS
    types = Counter(question.type for question in evalset.questions)
    for kind in QUESTION_TYPES:
        assert types[kind] >= MIN_PER_TYPE, kind
    for question in evalset.questions:
        if question.type == "cross-book":
            assert len({e.book for e in question.evidence}) >= 2, question.id  # noqa: PLR2004


def test_books_and_reports_are_ignored() -> None:
    """Git ignores the fetched EPUBs and the reports."""
    for path in ("eval/books/pg84.epub", "eval-reports/retrieval-x.json"):
        result = subprocess.run(  # noqa: S603 - fixed arguments
            ["git", "check-ignore", "-q", path],  # noqa: S607 - git on PATH
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, path
    tracked = subprocess.run(
        ["git", "check-ignore", "-q", "eval/retrieval.toml"],  # noqa: S607 - git on PATH
        cwd=ROOT,
        check=False,
    )
    assert tracked.returncode == 1


@pytest.mark.parametrize(
    ("script", "command"),
    [("eval-fetch-books", "fetch"), ("eval-retrieval", "run")],
)
def test_script_runs_its_command_with_the_eval_group(
    tmp_path: Path, script: str, command: str
) -> None:
    """Each script runs `librag.evaluation <command>` from the repo root."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text('#!/usr/bin/env bash\necho "$PWD | uv $*"\n', encoding="utf-8")
    uv.chmod(0o755)
    result = subprocess.run(  # noqa: S603 - the script is in the repo
        [str(ROOT / "scripts" / script), "--keep-books"],
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == (
        f"{ROOT} | uv run --group eval python -m librag.evaluation {command} "
        "--keep-books"
    )
