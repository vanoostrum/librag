# Copyright (C) 2026 Theo van Oostrum
"""Unit tests for the version route function."""

import tomllib
from pathlib import Path

from librag.main import version

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_returns_pyproject_version() -> None:
    """The version route returns the version declared in pyproject.toml."""
    expected = tomllib.loads(_PYPROJECT.read_text())["project"]["version"]
    assert version() == {"version": expected}
