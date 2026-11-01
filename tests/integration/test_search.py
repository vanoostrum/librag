# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for searching passages with POST /api/rag/search."""

import dataclasses
import hashlib
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update

from librag.db import books
from librag.main import create_app
from librag.passages import passage_id
from librag.settings import Settings
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

SEARCH = "/api/rag/search"
STAGES = ("dense", "bm25", "fusion")


def _book(identifier: str, title: str, author: str, *texts: str) -> FixtureBook:
    """Return a fixture book with one chapter, so one passage, per text."""
    return FixtureBook(
        identifier=identifier,
        title=title,
        author=author,
        chapters=tuple(
            FixtureChapter(paragraphs(text), nav_title=f"Part {n}")
            for n, text in enumerate(texts, start=1)
        ),
    )


def _id(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


SEA = _book(
    "urn:sea",
    "Sea Stories",
    "Ada Writer",
    "The lighthouse keeper polished the brass lamp every evening.",
    "Wild strawberries grew along the railway embankment.",
)
HARBOUR = _book(
    "urn:harbour",
    "Harbour Tales",
    "Ben Author",
    "A submarine captain charted the coral reef at dawn.",
    "The lighthouse beam swept across the harbour fog.",
)
SEA_ID = _id("urn:sea")
HARBOUR_ID = _id("urn:harbour")
KEEPER = passage_id(SEA_ID, 0)
BEAM = passage_id(HARBOUR_ID, 1)


@pytest.fixture
def index(client: TestClient, work: Callable[[], bool]) -> Callable[..., None]:
    """Return a function that uploads fixture books and indexes them."""

    def index(*fixtures: FixtureBook) -> None:
        for fixture in fixtures:
            files = {"file": ("book.epub", make_epub(fixture), "application/epub+zip")}
            response = client.post("/api/books", files=files)
            assert response.status_code == HTTPStatus.ACCEPTED, response.text
            assert work()

    return index


def search(client: TestClient, query: str, **fields: object) -> dict[str, Any]:
    """Search, check the response is 200, and return its body."""
    response = client.post(SEARCH, json={"query": query, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    return response.json()


def stage_ids(body: dict[str, Any], stage: str) -> list[str]:
    """Return the passage IDs of `stage`, in rank order."""
    return [item["passage_id"] for item in body["stages"][stage]["passages"]]


def result_ids(body: dict[str, Any]) -> list[str]:
    """Return the passage IDs of the results, in rank order."""
    return [result["passage_id"] for result in body["results"]]


PASSAGE_BOOKS = {
    passage_id(book_id, position): book_id
    for book_id in (SEA_ID, HARBOUR_ID)
    for position in range(2)
}


def all_book_ids(body: dict[str, Any]) -> set[str]:
    """Return the books of every passage in the results and the stages."""
    ids = set(result_ids(body)).union(*(stage_ids(body, stage) for stage in STAGES))
    return {PASSAGE_BOOKS[pid] for pid in ids}


def test_best_passage_is_first(client: TestClient, index: Callable[..., None]) -> None:
    """A query with words from one passage returns it first, with all its fields."""
    index(SEA)
    body = search(client, "lighthouse keeper brass lamp")
    assert body["query"] == "lighthouse keeper brass lamp"
    first = body["results"][0]
    assert first == {
        "rank": 1,
        "passage_id": KEEPER,
        "book_id": SEA_ID,
        "title": "Sea Stories",
        "author": "Ada Writer",
        "chapter": "Part 1",
        "section": None,
        "text": "The lighthouse keeper polished the brass lamp every evening.",
        "score": first["score"],
    }
    assert isinstance(first["score"], float)
    assert [result["rank"] for result in body["results"]] == list(
        range(1, len(body["results"]) + 1)
    )
    for stage in STAGES:
        assert stage_ids(body, stage)[0] == KEEPER, stage


def test_stages_list_ids_ranks_scores_and_time(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Each stage lists passage IDs, ranks and scores, and its time in ms."""
    index(SEA)
    body = search(client, "lighthouse keeper")
    assert set(body["stages"]) == set(STAGES)
    for stage in STAGES:
        entry = body["stages"][stage]
        assert set(entry) == {"passages", "time_ms"}
        assert entry["time_ms"] >= 0
        assert entry["passages"], stage
        for rank, item in enumerate(entry["passages"], start=1):
            assert set(item) == {"passage_id", "rank", "score"}
            assert item["rank"] == rank
            assert isinstance(item["score"], float)
    # BM25 only finds passages that share a word with the query.
    assert stage_ids(body, "bm25") == [KEEPER]
    assert set(stage_ids(body, "dense")) == {KEEPER, passage_id(SEA_ID, 1)}
    assert result_ids(body) == stage_ids(body, "fusion")


def test_limits_cap_results_and_stages(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Results hold at most top_k passages, and the stages dense_k and bm25_k."""
    many = _book(
        "urn:many",
        "Many Lights",
        "Ada Writer",
        *(f"Lighthouse number {n} shines over the bay." for n in range(6)),
    )
    index(many)
    body = search(client, "lighthouse", top_k=2, dense_k=3, bm25_k=4)
    assert len(body["results"]) == 2  # noqa: PLR2004
    assert len(stage_ids(body, "dense")) == 3  # noqa: PLR2004
    assert len(stage_ids(body, "bm25")) == 4  # noqa: PLR2004
    assert result_ids(body) == stage_ids(body, "fusion")[:2]


def test_results_come_from_both_books(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A query that matches a passage in each of two books returns both."""
    index(SEA, HARBOUR)
    body = search(client, "lighthouse")
    assert {KEEPER, BEAM} <= set(result_ids(body))
    assert {KEEPER, BEAM} == set(stage_ids(body, "bm25"))


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"book_ids": [SEA_ID]}, {SEA_ID}),
        ({"book_ids": [HARBOUR_ID]}, {HARBOUR_ID}),
        ({"authors": ["Ben Author"]}, {HARBOUR_ID}),
        ({"book_ids": [SEA_ID, HARBOUR_ID], "authors": ["Ada Writer"]}, {SEA_ID}),
        ({"book_ids": [SEA_ID], "authors": ["Ben Author"]}, set()),
        ({}, {SEA_ID, HARBOUR_ID}),
        ({"book_ids": [], "authors": []}, {SEA_ID, HARBOUR_ID}),
    ],
)
def test_filters_limit_results_and_stages(
    client: TestClient,
    index: Callable[..., None],
    filters: dict[str, list[str]],
    expected: set[str],
) -> None:
    """book_ids and authors limit the results and every stage, and combine.

    An empty list does not filter.
    """
    index(SEA, HARBOUR)
    body = search(client, "lighthouse", **filters)
    assert all_book_ids(body) == expected
    assert {result["book_id"] for result in body["results"]} == expected


def test_book_that_is_not_indexed_is_left_out(
    client: TestClient, index: Callable[..., None], engine: Engine
) -> None:
    """A book that is not in indexed never shows in the results or the stages."""
    index(SEA, HARBOUR)
    with engine.begin() as connection:
        connection.execute(
            update(books).where(books.c.id == HARBOUR_ID).values(status="indexing")
        )
    body = search(client, "lighthouse beam harbour fog")
    assert all_book_ids(body) == {SEA_ID}


def test_request_values_override_the_settings(
    settings: Settings, index: Callable[..., None]
) -> None:
    """Settings give the defaults, request values win, and the response shows both."""
    index(SEA, HARBOUR)
    tuned = dataclasses.replace(settings, search_top_k=1, dense_top_k=2, bm25_top_k=1)
    with TestClient(create_app(tuned)) as client:
        body = search(client, "lighthouse")
        assert body["settings"] == {
            "top_k": 1,
            "dense_k": 2,
            "bm25_k": 1,
            "embedding_model": "fake",
        }
        assert len(body["results"]) == 1
        assert len(stage_ids(body, "dense")) == 2  # noqa: PLR2004
        assert len(stage_ids(body, "bm25")) == 1

        body = search(client, "lighthouse", top_k=3, dense_k=4, bm25_k=2)
        assert body["settings"] == {
            "top_k": 3,
            "dense_k": 4,
            "bm25_k": 2,
            "embedding_model": "fake",
        }
        assert len(body["results"]) == 3  # noqa: PLR2004
        assert len(stage_ids(body, "dense")) == 4  # noqa: PLR2004
        assert len(stage_ids(body, "bm25")) == 2  # noqa: PLR2004


def test_default_settings(client: TestClient) -> None:
    """Without request values, search uses 10, 30 and 30."""
    body = search(client, "lighthouse")
    assert body["settings"] == {
        "top_k": 10,
        "dense_k": 30,
        "bm25_k": 30,
        "embedding_model": "fake",
    }


@pytest.mark.parametrize(
    ("request_body", "field"),
    [
        ({}, "query"),
        ({"query": ""}, "query"),
        ({"query": "   "}, "query"),
        ({"query": 3}, "query"),
        ({"query": "x", "top_k": 0}, "top_k"),
        ({"query": "x", "top_k": 101}, "top_k"),
        ({"query": "x", "dense_k": 0}, "dense_k"),
        ({"query": "x", "dense_k": 101}, "dense_k"),
        ({"query": "x", "bm25_k": 0}, "bm25_k"),
        ({"query": "x", "bm25_k": 101}, "bm25_k"),
        ({"query": "x", "book_ids": "not a list"}, "book_ids"),
    ],
)
def test_invalid_request_is_refused(
    client: TestClient, request_body: dict[str, object], field: str
) -> None:
    """A missing or blank query, or a limit outside 1 to 100, returns 422."""
    response = client.post(SEARCH, json=request_body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text
    assert list(response.json()) == ["error"]
    assert response.json()["error"].startswith(f"{field}: ")


def test_body_that_is_not_json_is_refused(client: TestClient) -> None:
    """A body that is not JSON returns 422 with an error."""
    response = client.post(
        SEARCH, content=b"query=x", headers={"content-type": "application/json"}
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": "JSON decode error"}


def test_limits_of_1_and_100_are_accepted(client: TestClient) -> None:
    """1 and 100 are inside the range."""
    search(client, "x", top_k=1, dense_k=100, bm25_k=1)
    search(client, "x", top_k=100, dense_k=1, bm25_k=100)


def _empty(body: dict[str, Any]) -> bool:
    lists = [body["results"], *(body["stages"][stage]["passages"] for stage in STAGES)]
    return not any(lists)


def test_empty_library_returns_empty_lists(client: TestClient) -> None:
    """With no books, search returns 200 with empty results and stages."""
    assert _empty(search(client, "lighthouse"))


def test_library_without_indexed_books_returns_empty_lists(
    client: TestClient, index: Callable[..., None], engine: Engine
) -> None:
    """With books that are all still indexing, search returns empty lists."""
    index(SEA)
    with engine.begin() as connection:
        connection.execute(update(books).values(status="indexing"))
    assert _empty(search(client, "lighthouse"))


def test_unknown_book_filter_returns_empty_lists(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A filter on a book ID that is not in the library returns empty lists."""
    index(SEA)
    assert _empty(search(client, "lighthouse", book_ids=["0000000000000000"]))
    assert _empty(search(client, "lighthouse", authors=["Nobody"]))
