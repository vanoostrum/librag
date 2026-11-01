# Copyright (C) 2026 Theo van Oostrum
"""The running stack deletes an indexed book. Run: uv run pytest tests/e2e."""

import os
import time
import uuid
from http import HTTPStatus
from typing import Any

import httpx2

from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

BASE_URL = os.environ.get("LIBRAG_E2E_URL", "http://localhost:8000")
INDEX_TIMEOUT_SECONDS = 60


def _search(word: str) -> list[dict[str, Any]]:
    response = httpx2.post(
        f"{BASE_URL}/api/rag/search", json={"query": f"{word} ferry"}, timeout=10.0
    )
    assert response.status_code == HTTPStatus.OK, response.text
    return response.json()["results"]


def test_deleted_book_is_no_longer_found() -> None:
    """Upload and index a book, delete it: search no longer finds its passage."""
    # A new word and identifier per run, so the test also passes on a used stack.
    word = f"zq{uuid.uuid4().hex[:10]}"
    book = FixtureBook(
        identifier=f"urn:uuid:{uuid.uuid4()}",
        title="Delete End to End",
        chapters=(FixtureChapter(paragraphs(f"The {word} ferry crossed at dawn.")),),
    )
    files = {"file": ("delete.epub", make_epub(book), "application/epub+zip")}
    response = httpx2.post(f"{BASE_URL}/api/books", files=files, timeout=10.0)
    assert response.status_code == HTTPStatus.ACCEPTED, response.text
    book_id = response.json()["id"]

    deadline = time.monotonic() + INDEX_TIMEOUT_SECONDS
    listed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        books = httpx2.get(f"{BASE_URL}/api/books", timeout=5.0).json()["books"]
        listed = next(b for b in books if b["id"] == book_id)
        if listed["status"] not in {"queued", "parsing", "indexing"}:
            break
        time.sleep(0.5)
    assert listed["status"] == "indexed", listed
    assert book_id in {result["book_id"] for result in _search(word)}

    response = httpx2.delete(f"{BASE_URL}/api/books/{book_id}", timeout=10.0)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.text
    assert book_id not in {result["book_id"] for result in _search(word)}
    books = httpx2.get(f"{BASE_URL}/api/books", timeout=5.0).json()["books"]
    assert book_id not in {b["id"] for b in books}
