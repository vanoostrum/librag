# Copyright (C) 2026 Theo van Oostrum
"""The POC's definition of done: a cross-book question, with citations and diagnostics.

Three books are uploaded and indexed; a question that needs two of them is
asked with those two selected, whole and streamed, once per chat model. With
the fakes the books are the tiny set; in a live run they are the live set.
Run: uv run pytest tests/e2e.
"""

from dataclasses import dataclass
from typing import Any

import pytest

from tests.e2e import stack
from tests.e2e.books import LIVE as LIVE_BOOKS
from tests.e2e.books import TINY, fresh
from tests.e2e.live import LIVE

CITED_FIELDS = ("book_id", "title", "chapter", "section", "text")


@dataclass(frozen=True)
class Indexed:
    """The indexed books, and the question that needs the two selected ones."""

    selected: list[str]
    other: str
    question: str


@pytest.fixture(scope="module")
def indexed() -> Indexed:
    """Upload the three books of this run's set and wait until each is indexed."""
    library = LIVE_BOOKS if LIVE else TINY
    ids = [stack.upload(fresh(book)) for book in library.books]
    for book_id in ids:
        stack.wait_until_indexed(book_id)
    return Indexed(selected=ids[:2], other=ids[2], question=library.question)


def _check_diagnostics(details: dict[str, Any], indexed: Indexed) -> set[str]:
    """Check the context and every citation against the selected books.

    Return the IDs of the books that the answer cites.
    """
    retrieval = details["retrieval"]
    candidates = {c["passage_id"]: c for c in retrieval["candidates"]}
    context = retrieval["context"]["passage_ids"]
    assert context, "the context is empty"
    assert retrieval["context"]["tokens"] > 0
    # The context holds passages from both selected books, and from no other.
    assert {candidates[p]["book_id"] for p in context} == set(indexed.selected)

    citations = details["citations"]
    assert citations, "the answer cites no passage"
    assert [citation["n"] for citation in citations] == list(
        range(1, len(citations) + 1)
    )
    for citation in citations:
        assert citation["passage_id"] in context, citation
        passage = candidates[citation["passage_id"]]
        assert {key: citation[key] for key in CITED_FIELDS} == {
            key: passage[key] for key in CITED_FIELDS
        }
        assert citation["book_id"] in indexed.selected
        assert citation["chapter"]
        assert citation["text"]

    settings, rerank = retrieval["settings"], retrieval["stages"]["rerank"]
    assert rerank["passages"], "the rerank stage scored no passage"
    assert all(isinstance(p["score"], float) for p in rerank["passages"])
    # A live run uses the CrossEncoder in the image, never the fake reranker.
    if LIVE:
        assert settings["reranker_model"] != "fake"
    else:
        assert settings["reranker_model"] == "fake"
    return {citation["book_id"] for citation in citations}


def _check_parts(parts: list[dict[str, Any]], citations: list[dict[str, Any]]) -> None:
    """Each part's citations are numbers of the answer's citations."""
    assert parts, "the answer has no parts"
    numbers = {citation["n"] for citation in citations}
    for part in parts:
        assert part["kind"] in {"book", "synthesis", "general"}, part
        assert part["text"], part
        assert set(part["citations"]) <= numbers, part


def test_cross_book_question_cites_the_selected_books(
    model: str, indexed: Indexed
) -> None:
    """POST /api/chat answers from both selected books, with valid citations."""
    body = stack.chat(model, indexed.question, indexed.selected)
    assert body["model"] == model
    cited = _check_diagnostics(body, indexed)
    _check_parts(body["parts"], body["citations"])
    assert indexed.other not in cited
    if LIVE:
        assert cited == set(indexed.selected), "the answer cites only one book"


def test_cross_book_question_streams_status_parts_and_done(
    model: str, indexed: Indexed
) -> None:
    """The stream sends status, then parts, then done with matching diagnostics."""
    events = stack.chat_stream(model, indexed.question, indexed.selected)
    names = [name for name, _ in events]
    assert "error" not in names, events[-1]
    assert names[-1] == "done"
    assert names.count("done") == 1
    statuses = [data["step"] for name, data in events if name == "status"]
    assert statuses == ["searching", "writing"]
    first_part = names.index("part")
    assert set(names[:first_part]) == {"status"}
    assert set(names[first_part:-1]) == {"part"}

    done = events[-1][1]
    assert done["model"] == model
    assert set(done["usage"]) == {
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
    }
    cited = _check_diagnostics(done, indexed)
    parts = [data for name, data in events if name == "part"]
    _check_parts(parts, done["citations"])
    by_number = {citation["n"]: citation for citation in done["citations"]}
    for part in parts:
        assert [source["n"] for source in part["sources"]] == part["citations"]
        for source in part["sources"]:
            assert source == by_number[source["n"]]
    assert indexed.other not in cited
    if LIVE:
        assert cited == set(indexed.selected), "the answer cites only one book"
