# Copyright (C) 2026 Theo van Oostrum
"""The running stack answers a question with citations, whole and streamed.

These tests check what the fake LLM cites, so a live run skips them; the
cross-book tests cover the real models. Run: uv run pytest tests/e2e.
"""

import uuid

import pytest

from tests.e2e import stack
from tests.epubs import FixtureBook, FixtureChapter, paragraphs

pytestmark = pytest.mark.fake_only


def _index_book() -> tuple[str, str]:
    """Upload a fixture book, wait until it is indexed; return its ID and word."""
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
    return str(stack.index(book)["id"]), word


def test_chat_answers_with_citations_to_an_indexed_book(model: str) -> None:
    """Upload a book, wait for indexed, and ask: the answer cites its passages."""
    book_id, word = _index_book()
    body = stack.chat(model, f"Who polished the {word} lamp?", [book_id])
    [claim] = [part for part in body["parts"] if part["kind"] == "book"]
    assert claim["citations"]
    cited = {citation["n"]: citation for citation in body["citations"]}
    assert set(claim["citations"]) <= set(cited)
    first = cited[claim["citations"][0]]
    assert first["book_id"] == book_id
    assert first["chapter"] == "Keeper"
    assert word in first["text"]


def test_chat_streams_cited_parts_and_done(model: str) -> None:
    """The stream sends parts whose citations resolve to the book, then done."""
    book_id, word = _index_book()
    events = stack.chat_stream(model, f"Who polished the {word} lamp?", [book_id])
    assert events[-1][0] == "done"
    [claim] = [
        data for name, data in events if name == "part" and data["kind"] == "book"
    ]
    assert claim["citations"]
    assert [source["n"] for source in claim["sources"]] == claim["citations"]
    assert claim["sources"][0]["book_id"] == book_id
    assert word in claim["sources"][0]["text"]
