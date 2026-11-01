# Copyright (C) 2026 Theo van Oostrum
"""The running stack answers /health and /version. Run: uv run pytest tests/e2e."""

import tomllib
from http import HTTPStatus
from pathlib import Path

import httpx2

from tests.e2e import stack

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_health() -> None:
    """The stack is ready: Qdrant, the database and the worker are all ok."""
    response = httpx2.get(f"{stack.BASE_URL}/health", timeout=5.0)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "status": "ok",
        "checks": {"qdrant": "ok", "database": "ok", "worker": "ok"},
    }


def test_version() -> None:
    """The stack runs the version that pyproject.toml declares."""
    expected = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    response = httpx2.get(f"{stack.BASE_URL}/version", timeout=5.0)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"version": expected}
