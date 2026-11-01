# Copyright (C) 2026 Theo van Oostrum
"""The running stack indexes an uploaded EPUB. Run: uv run pytest tests/e2e."""

import uuid
from http import HTTPStatus

import httpx2

from tests.e2e import stack
from tests.e2e.live import LIVE
from tests.epubs import FixtureBook, FixtureChapter, paragraphs


def test_upload_is_indexed_by_the_worker() -> None:
    """An uploaded EPUB reaches indexed, with all its passages indexed."""
    # A new identifier per run, so the test also passes on a stack it used before.
    book = FixtureBook(
        identifier=f"urn:uuid:{uuid.uuid4()}",
        title="End to End",
        chapters=(
            FixtureChapter(paragraphs("The first chapter."), nav_title="One"),
            FixtureChapter(paragraphs("The second chapter."), nav_title="Two"),
        ),
    )
    listed = stack.index(book)
    assert listed["passages_total"] == 2, listed  # noqa: PLR2004
    assert listed["passages_indexed"] == listed["passages_total"], listed
    assert listed["embedding_tokens"] > 0, listed
    if LIVE:
        # The real embedder's cost, or None when LiteLLM has no price for it.
        assert listed["embedding_cost_usd"] is None or listed["embedding_cost_usd"] > 0
    else:
        assert listed["embedding_cost_usd"] == 0.0, "the stack uses the fake embedder"


def test_uploaded_book_is_on_the_library_page() -> None:
    """The Library page at / lists an uploaded book by its title."""
    title = f"Library Page {uuid.uuid4().hex[:8]}"
    book_id = stack.upload(
        FixtureBook(identifier=f"urn:uuid:{uuid.uuid4()}", title=title)
    )

    page = httpx2.get(f"{stack.BASE_URL}/", timeout=5.0)
    assert page.status_code == HTTPStatus.OK
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert f'<h2 class="book-card__title">{title}</h2>' in page.text
    # Wait for the worker, so a live run logs what embedding the book cost.
    stack.wait_until_indexed(book_id)
