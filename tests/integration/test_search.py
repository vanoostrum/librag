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
from librag.passages import count_tokens, passage_id
from librag.settings import Settings
from tests.epubs import FixtureBook, FixtureChapter, paragraphs

SEARCH = "/api/rag/search"
STAGES = ("dense", "bm25", "fusion", "rerank")


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
        "fusion_score": first["fusion_score"],
        "rerank_score": first["rerank_score"],
    }
    assert isinstance(first["fusion_score"], float)
    assert isinstance(first["rerank_score"], float)
    assert first["score"] == first["rerank_score"]
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
    # The reranker scores every fused candidate.
    assert set(stage_ids(body, "rerank")) == set(stage_ids(body, "fusion"))
    assert len(stage_ids(body, "rerank")) == len(stage_ids(body, "fusion"))
    assert result_ids(body) == stage_ids(body, "rerank")


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
    assert result_ids(body) == stage_ids(body, "rerank")[:2]

    # fusion_k caps the fused candidates, and the reranker scores each of them.
    body = search(client, "lighthouse", dense_k=6, bm25_k=6, fusion_k=5)
    assert len(stage_ids(body, "fusion")) == 5  # noqa: PLR2004
    assert len(stage_ids(body, "rerank")) == 5  # noqa: PLR2004

    body = search(client, "lighthouse", dense_k=3, bm25_k=4, fusion_k=2)
    assert len(stage_ids(body, "fusion")) == 2  # noqa: PLR2004
    assert len(stage_ids(body, "rerank")) == 2  # noqa: PLR2004


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
    tuned = dataclasses.replace(
        settings,
        search_top_k=1,
        dense_top_k=2,
        bm25_top_k=1,
        fusion_top_k=2,
        context_token_budget=200,
    )
    with TestClient(create_app(tuned)) as client:
        body = search(client, "lighthouse")
        assert body["settings"] == {
            "top_k": 1,
            "dense_k": 2,
            "bm25_k": 1,
            "fusion_k": 2,
            "token_budget": 200,
            "rerank": True,
            "embedding_model": "fake",
            "reranker_model": "fake",
        }
        assert len(body["results"]) == 1
        assert len(stage_ids(body, "dense")) == 2  # noqa: PLR2004
        assert len(stage_ids(body, "bm25")) == 1
        assert len(stage_ids(body, "fusion")) == 2  # noqa: PLR2004

        body = search(
            client,
            "lighthouse",
            top_k=3,
            dense_k=4,
            bm25_k=2,
            fusion_k=4,
            token_budget=300,
            rerank=False,
        )
        assert body["settings"] == {
            "top_k": 3,
            "dense_k": 4,
            "bm25_k": 2,
            "fusion_k": 4,
            "token_budget": 300,
            "rerank": False,
            "embedding_model": "fake",
            "reranker_model": "fake",
        }
        assert len(body["results"]) == 3  # noqa: PLR2004
        assert len(stage_ids(body, "dense")) == 4  # noqa: PLR2004
        assert len(stage_ids(body, "bm25")) == 2  # noqa: PLR2004
        assert len(stage_ids(body, "fusion")) == 4  # noqa: PLR2004


def test_default_settings(client: TestClient) -> None:
    """Without request values, search uses the defaults, with reranking on."""
    body = search(client, "lighthouse")
    assert body["settings"] == {
        "top_k": 10,
        "dense_k": 30,
        "bm25_k": 30,
        "fusion_k": 30,
        "token_budget": 4000,
        "rerank": True,
        "embedding_model": "fake",
        "reranker_model": "fake",
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
        ({"query": "x", "fusion_k": 0}, "fusion_k"),
        ({"query": "x", "fusion_k": 101}, "fusion_k"),
        ({"query": "x", "token_budget": 99}, "token_budget"),
        ({"query": "x", "token_budget": 32001}, "token_budget"),
        ({"query": "x", "rerank": "maybe"}, "rerank"),
        ({"query": "x", "book_ids": "not a list"}, "book_ids"),
    ],
)
def test_invalid_request_is_refused(
    client: TestClient, request_body: dict[str, object], field: str
) -> None:
    """A missing or blank query, or a limit out of its range, returns 422.

    The k values are 1 to 100, and token_budget is 100 to 32000.
    """
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
    """The ends of each range are accepted: 1 and 100, and 100 and 32000."""
    search(client, "x", top_k=1, dense_k=100, bm25_k=1, fusion_k=100, token_budget=100)
    search(
        client, "x", top_k=100, dense_k=1, bm25_k=100, fusion_k=1, token_budget=32000
    )


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


# Fusion ranks SHORT first: it repeats two of the query's three words. FULL holds
# all three, once each, among other words. ONE holds one of them.
SHORT = "Lighthouse beacon, lighthouse beacon: the lighthouse beacon on the cape."
FULL = (
    "Far along the windswept coast, past the old harbour wall and the fishing "
    "boats, the keeper climbed the lighthouse stairs at dusk to light the beacon."
)
ONE = "The keeper slept."
QUERY = "lighthouse beacon keeper"
RANKED = _book("urn:ranked", "Ranked", "Ada Writer", SHORT, FULL, ONE)
RANKED_ID = _id("urn:ranked")
SHORT_ID, FULL_ID, ONE_ID = (passage_id(RANKED_ID, n) for n in range(3))


def test_results_follow_the_rerank_order(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Reranking puts the passage with all query words above fusion's first one.

    Each result shows its fusion score and its rerank score.
    """
    index(RANKED)
    body = search(client, QUERY)
    assert stage_ids(body, "fusion") == [SHORT_ID, FULL_ID, ONE_ID]
    assert stage_ids(body, "rerank") == [FULL_ID, SHORT_ID, ONE_ID]
    assert result_ids(body) == [FULL_ID, SHORT_ID, ONE_ID]
    rerank = {
        item["passage_id"]: item["score"]
        for item in body["stages"]["rerank"]["passages"]
    }
    fusion = {
        item["passage_id"]: item["score"]
        for item in body["stages"]["fusion"]["passages"]
    }
    assert rerank[FULL_ID] > rerank[SHORT_ID]
    for rank, result in enumerate(body["results"], start=1):
        assert result["rank"] == rank
        assert result["rerank_score"] == rerank[result["passage_id"]]
        assert result["fusion_score"] == fusion[result["passage_id"]]
        assert result["score"] == result["rerank_score"]


def test_rerank_off_keeps_the_fusion_order(
    client: TestClient, index: Callable[..., None]
) -> None:
    """With rerank false, results follow fusion, without rerank scores or stage."""
    index(RANKED)
    body = search(client, QUERY, rerank=False)
    assert result_ids(body) == stage_ids(body, "fusion") == [SHORT_ID, FULL_ID, ONE_ID]
    assert body["stages"]["rerank"] == {"passages": [], "time_ms": 0.0}
    fusion = {
        item["passage_id"]: item["score"]
        for item in body["stages"]["fusion"]["passages"]
    }
    for result in body["results"]:
        assert result["rerank_score"] is None
        assert result["fusion_score"] == fusion[result["passage_id"]]
        assert result["score"] == result["fusion_score"]


def test_fake_reranker_scores_the_share_of_query_words(
    client: TestClient, index: Callable[..., None]
) -> None:
    """The fake reranker gives a passage the share of query words it contains."""
    index(RANKED)
    body = search(client, QUERY)
    rerank = {
        item["passage_id"]: item["score"]
        for item in body["stages"]["rerank"]["passages"]
    }
    assert rerank == {FULL_ID: 1.0, SHORT_ID: 2 / 3, ONE_ID: 1 / 3}


# About 150 tokens with all query words, so it ranks first and fills a budget of 100.
LONG = " ".join(["The lighthouse keeper lit the beacon and logged every ship."] * 12)
BUDGETED = _book("urn:budget", "Budget", "Ada Writer", LONG, SHORT)
BUDGET_ID = _id("urn:budget")


def test_passage_over_the_budget_is_skipped(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A passage that does not fit the remaining budget is skipped.

    A later passage that fits is still added.
    """
    long_id, short_id = passage_id(BUDGET_ID, 0), passage_id(BUDGET_ID, 1)
    assert count_tokens(LONG) > 100  # noqa: PLR2004
    assert count_tokens(SHORT) <= 100  # noqa: PLR2004
    index(BUDGETED)
    body = search(client, QUERY, token_budget=100)
    assert stage_ids(body, "rerank") == [long_id, short_id]
    assert result_ids(body) == [short_id]
    assert body["results"][0]["rank"] == 1

    # With room for it, the long passage comes first.
    body = search(client, QUERY, token_budget=1000)
    assert result_ids(body) == [long_id, short_id]


def test_results_stay_within_top_k_and_the_budget(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Results never hold more than top_k passages or token_budget tokens."""
    many = _book(
        "urn:budget-many",
        "Many",
        "Ada Writer",
        *(
            f"Lighthouse {n}: " + "the keeper trimmed the wick. " * n
            for n in range(1, 13)
        ),
    )
    index(many)
    for top_k, budget in ((3, 32000), (10, 100), (10, 150), (5, 400)):
        body = search(client, "lighthouse keeper", top_k=top_k, token_budget=budget)
        texts = [result["text"] for result in body["results"]]
        assert texts, (top_k, budget)
        assert len(texts) <= top_k
        assert sum(count_tokens(text) for text in texts) <= budget
        assert len(stage_ids(body, "rerank")) == 12  # noqa: PLR2004


def test_query_without_words_scores_zero(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A query of only punctuation still returns 200; the fake reranker scores 0."""
    index(RANKED)
    body = search(client, "?!")
    assert all(item["score"] == 0.0 for item in body["stages"]["rerank"]["passages"])
    assert result_ids(body) == stage_ids(body, "fusion")


def test_candidates_hold_the_text_of_every_staged_passage(
    client: TestClient, index: Callable[..., None]
) -> None:
    """`candidates` lists each passage of any stage once, with its book and text."""
    index(SEA, HARBOUR)
    body = search(client, "lighthouse", fusion_k=1)
    staged = [stage_ids(body, stage) for stage in ("fusion", "dense", "bm25")]
    ids = list(dict.fromkeys(pid for stage in staged for pid in stage))
    assert len(ids) == len(PASSAGE_BOOKS)
    assert [candidate["passage_id"] for candidate in body["candidates"]] == ids
    assert {c["passage_id"]: c for c in body["candidates"]}[BEAM] == {
        "passage_id": BEAM,
        "book_id": HARBOUR_ID,
        "title": "Harbour Tales",
        "chapter": "Part 2",
        "section": None,
        "text": "The lighthouse beam swept across the harbour fog.",
    }
    # Fusion keeps one passage; the others come from dense and BM25 only.
    assert len(stage_ids(body, "fusion")) == 1


def test_candidates_are_the_only_new_field(client: TestClient) -> None:
    """The response keeps its fields and adds `candidates`, empty with no books."""
    body = search(client, "lighthouse")
    assert set(body) == {"query", "results", "stages", "settings", "candidates"}
    assert body["candidates"] == []
