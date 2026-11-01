# Copyright (C) 2026 Theo van Oostrum
"""The running stack searches an indexed book. Run: uv run pytest tests/e2e."""

import uuid
from http import HTTPStatus

import httpx2

from tests.e2e import stack
from tests.epubs import FixtureBook, FixtureChapter, paragraphs


def test_search_finds_the_passage_of_an_indexed_book() -> None:
    """Upload a book, wait for indexed, and search: the expected passage is first."""
    # A new identifier per run, so the test also passes on a stack it used before.
    word = f"zq{uuid.uuid4().hex[:10]}"
    book = FixtureBook(
        identifier=f"urn:uuid:{uuid.uuid4()}",
        title="Search End to End",
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
    book_id = str(stack.index(book)["id"])

    response = httpx2.post(
        f"{stack.BASE_URL}/api/rag/search",
        json={"query": f"{word} lighthouse keeper", "book_ids": [book_id]},
        timeout=10.0,
    )
    assert response.status_code == HTTPStatus.OK, response.text
    first = response.json()["results"][0]
    assert first["book_id"] == book_id
    assert first["chapter"] == "Keeper"
    assert word in first["text"]
