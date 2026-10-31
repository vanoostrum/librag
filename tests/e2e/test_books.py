# Copyright (C) 2026 Theo van Oostrum
"""The running stack parses an uploaded EPUB. Run: uv run pytest tests/e2e."""

import os
import time
import uuid
from http import HTTPStatus
from typing import Any

import httpx2

from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

BASE_URL = os.environ.get("LIBRAG_E2E_URL", "http://localhost:8000")
PARSE_TIMEOUT_SECONDS = 60


def test_upload_is_parsed_by_the_worker() -> None:
    """An uploaded EPUB reaches indexing with its passages counted."""
    # A new identifier per run, so the test also passes on a stack it used before.
    book = FixtureBook(
        identifier=f"urn:uuid:{uuid.uuid4()}",
        title="End to End",
        chapters=(
            FixtureChapter(paragraphs("The first chapter."), nav_title="One"),
            FixtureChapter(paragraphs("The second chapter."), nav_title="Two"),
        ),
    )
    files = {"file": ("e2e.epub", make_epub(book), "application/epub+zip")}
    response = httpx2.post(f"{BASE_URL}/api/books", files=files, timeout=10.0)
    assert response.status_code == HTTPStatus.ACCEPTED, response.text
    book_id = response.json()["id"]
    assert response.json()["status"] == "queued"

    deadline = time.monotonic() + PARSE_TIMEOUT_SECONDS
    listed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        books = httpx2.get(f"{BASE_URL}/api/books", timeout=5.0).json()["books"]
        listed = next(b for b in books if b["id"] == book_id)
        if listed["status"] not in {"queued", "parsing"}:
            break
        time.sleep(0.5)
    assert listed["status"] == "indexing", listed
    assert listed["passages_indexed"] == 0
    assert isinstance(listed["passages_total"], int)
    assert listed["passages_total"] > 0
