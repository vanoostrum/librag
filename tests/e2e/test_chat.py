# Copyright (C) 2026 Theo van Oostrum
"""The running stack answers a question with citations. Run: uv run pytest tests/e2e."""

import os
import time
import uuid
from http import HTTPStatus
from typing import Any

import httpx2

from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

BASE_URL = os.environ.get("LIBRAG_E2E_URL", "http://localhost:8000")
INDEX_TIMEOUT_SECONDS = 60


def test_chat_answers_with_citations_to_an_indexed_book() -> None:
    """Upload a book, wait for indexed, and ask: the answer cites its passages."""
    # A new identifier per run, so the test also passes on a stack it used before.
    word = f"zq{uuid.uuid4().hex[:10]}"
    book = FixtureBook(
        identifier=f"urn:uuid:{uuid.uuid4()}",
        title="Chat End to End",
        chapters=(
            FixtureChapter(
                paragraphs(f"The {word} lighthouse keeper polished the brass lamp."),
                nav_title="Keeper",
            ),
            FixtureChapter(
                paragraphs("Wild strawberries grew along the railway embankment."),
                nav_title="Berries",
            ),
        ),
    )
    files = {"file": ("chat.epub", make_epub(book), "application/epub+zip")}
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

    response = httpx2.post(
        f"{BASE_URL}/api/chat",
        json={"question": f"Who polished the {word} lamp?", "book_ids": [book_id]},
        timeout=30.0,
    )
    assert response.status_code == HTTPStatus.OK, response.text
    body = response.json()
    [claim] = [part for part in body["parts"] if part["kind"] == "book"]
    assert claim["citations"]
    cited = {citation["n"]: citation for citation in body["citations"]}
    assert set(claim["citations"]) <= set(cited)
    first = cited[claim["citations"][0]]
    assert first["book_id"] == book_id
    assert first["chapter"] == "Keeper"
    assert word in first["text"]
