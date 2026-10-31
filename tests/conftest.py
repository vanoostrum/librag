# Copyright (C) 2026 Theo van Oostrum
"""Fixtures shared by the LibRag tests."""

import os
from pathlib import Path

import httpx2
import pytest

from librag.db import upgrade

DEFAULT_QDRANT_URL = "http://localhost:6333"


@pytest.fixture(scope="session")
def qdrant_url() -> str:
    """Return the URL of a running Qdrant, or fail with how to start one."""
    url = os.environ.get("LIBRAG_QDRANT_URL", DEFAULT_QDRANT_URL)
    try:
        httpx2.get(f"{url}/readyz", timeout=2.0).raise_for_status()
    except httpx2.HTTPError as error:
        pytest.fail(
            f"This test needs Qdrant, but {url} is not ready ({error}). Start it "
            "with `docker compose up -d qdrant`, or point LIBRAG_QDRANT_URL at one. "
            "See the project-verify skill.",
            pytrace=False,
        )
    return url


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """Return the URL of a new SQLite database, migrated to the latest schema."""
    url = f"sqlite:///{tmp_path / 'librag.db'}"
    upgrade(url)
    return url
