# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for splitting a complex question into sub-questions (LIBRAG_DECOMPOSE).

Chat and its stream split the search query when the switch is on; search splits
it when the request asks for `decompose`. The fake LLM splits on " and ".
"""

import dataclasses
from collections.abc import Callable, Iterator
from http import HTTPStatus
from typing import Any, override

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from librag.llm import Completion, FakeLlm, LlmError
from librag.main import create_app
from librag.passages import passage_id
from librag.prompts import AnswerPrompt, DecomposePrompt, Prompt, RewritePrompt
from librag.rerank import FakeReranker
from librag.settings import Settings
from tests.integration.test_chat import (
    HARBOUR,
    SEA,
    SEA_ID,
    TURNS,
    answer,
    ask,
    reply,
    script,
    usage_rows,
)
from tests.integration.test_chat_stream import named, stream

SEARCH = "/api/rag/search"
SPLIT = "lighthouse keeper and wild strawberries and harbour fog"
SUBQUESTIONS = ["lighthouse keeper", "wild strawberries", "harbour fog"]
BRASS = passage_id(SEA_ID, 0)
STRAWBERRIES = passage_id(SEA_ID, 2)


def queries_reply(*queries: str) -> Completion:
    """Return a decompose reply that lists `queries`."""
    quoted = ", ".join(f'"{query}"' for query in queries)
    return reply(f'{{"queries": [{quoted}]}}')


def ids(stage: dict[str, Any]) -> list[str]:
    """Return the passage IDs of a stage, in rank order."""
    return [item["passage_id"] for item in stage["passages"]]


def search(client: TestClient, query: str, **fields: object) -> dict[str, Any]:
    """Search, check the response is 200, and return its body."""
    response = client.post(SEARCH, json={"query": query, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    return response.json()


class RecordingReranker(FakeReranker):
    """The fake reranker, recording the query it scores against."""

    def __init__(self) -> None:
        """Start with no recorded queries."""
        self.queries: list[str] = []

    @override
    def score(self, query: str, texts: list[str]) -> list[float]:
        """Record `query`, then score like the fake reranker."""
        self.queries.append(query)
        return super().score(query, texts)


class ModelLlm(FakeLlm):
    """The fake LLM, recording the model and prompt of each call."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[tuple[str, Prompt]] = []

    @override
    def complete(self, model: str, prompt: Prompt) -> Completion:
        """Record the call, then reply like the fake LLM."""
        self.calls.append((model, prompt))
        return super().complete(model, prompt)


@pytest.fixture
def split_settings(settings: Settings) -> Settings:
    """Return the test settings with LIBRAG_DECOMPOSE on, and 1 passage per list.

    With one dense and one BM25 passage per query, each sub-question's fusion
    list holds only the passages that it finds best.
    """
    return dataclasses.replace(settings, decompose=True, dense_top_k=1, bm25_top_k=1)


@pytest.fixture
def split(split_settings: Settings, client: TestClient) -> Iterator[TestClient]:
    """Return a client for the app with LIBRAG_DECOMPOSE on.

    It shares the stores of `client`, so a book indexed through one shows in both.
    """
    del client
    with TestClient(create_app(split_settings)) as split:
        yield split


def check_found_by(retrieval: dict[str, Any]) -> dict[str, list[str]]:
    """Check each candidate's `found_by`, and return it by passage ID."""
    found_by: dict[str, list[str]] = {
        c["passage_id"]: c["found_by"] for c in retrieval["candidates"]
    }
    for passage, queries in found_by.items():
        assert queries == [
            query["id"]
            for query in retrieval["queries"]
            if passage in ids(query["stages"]["fusion"])
        ]
    return found_by


def test_off_makes_no_decompose_call(
    client: TestClient, index: Callable[..., None]
) -> None:
    """With the switch off, chat searches the one search query, listed as Q1."""
    index(SEA, HARBOUR)
    llm = script(client, reply(answer()))
    body = ask(client, SPLIT)
    assert [type(prompt) for prompt in llm.prompts] == [AnswerPrompt]
    retrieval = body["retrieval"]
    [query] = retrieval["queries"]
    assert query["id"] == "Q1"
    assert query["text"] == body["search_query"] == SPLIT
    stages = retrieval["stages"]
    assert query["stages"] == {key: stages[key] for key in ("dense", "bm25", "fusion")}
    found_by = check_found_by(retrieval)
    assert {passage: ["Q1"] for passage in ids(stages["fusion"])}.items() <= (
        found_by.items()
    )


def test_unsplit_question_is_one_search(
    split: TestClient, index: Callable[..., None]
) -> None:
    """A question the LLM does not split gives Q1 only, after one decompose call."""
    index(SEA, HARBOUR)
    llm = script(split, queries_reply("lighthouse keeper"), reply(answer()))
    body = ask(split, "lighthouse keeper")
    assert [type(prompt) for prompt in llm.prompts] == [DecomposePrompt, AnswerPrompt]
    [query] = body["retrieval"]["queries"]
    assert (query["id"], query["text"]) == ("Q1", "lighthouse keeper")
    found_by = check_found_by(body["retrieval"])
    assert {q for queries in found_by.values() for q in queries} == {"Q1"}


def test_split_question_searches_each_subquestion(
    split: TestClient, index: Callable[..., None]
) -> None:
    """A split into 3 gives Q1 to Q3, their dense, BM25 and fusion lists, and fusion."""
    index(SEA, HARBOUR)
    body = ask(split, SPLIT)
    retrieval = body["retrieval"]
    queries = retrieval["queries"]
    assert [(q["id"], q["text"]) for q in queries] == [
        ("Q1", SUBQUESTIONS[0]),
        ("Q2", SUBQUESTIONS[1]),
        ("Q3", SUBQUESTIONS[2]),
    ]
    for query in queries:
        assert set(query["stages"]) == {"dense", "bm25", "fusion"}
        assert len(query["stages"]["dense"]["passages"]) == 1
        assert len(query["stages"]["bm25"]["passages"]) == 1
    stages = retrieval["stages"]
    fused = {p for query in queries for p in ids(query["stages"]["fusion"])}
    assert set(ids(stages["fusion"])) == fused
    assert set(ids(stages["rerank"])) == fused
    assert body["search_query"] == SPLIT


def test_candidates_carry_found_by_and_best_ranks(
    split: TestClient, index: Callable[..., None]
) -> None:
    """`found_by` names the sub-questions that fused a passage; ranks are the best."""
    index(SEA, HARBOUR)
    both = search(split, "brass lamp and polished brass", decompose=True)
    assert check_found_by(both)[BRASS] == ["Q1", "Q2"]
    body = search(split, SPLIT, decompose=True, dense_k=3, bm25_k=3)
    found_by = check_found_by(body)
    assert "Q2" in found_by[STRAWBERRIES]
    for stage in ("dense", "bm25"):
        best: dict[str, int] = {}
        for query in body["queries"]:
            for item in query["stages"][stage]["passages"]:
                best[item["passage_id"]] = min(
                    item["rank"], best.get(item["passage_id"], item["rank"])
                )
        ranks = {i["passage_id"]: i["rank"] for i in body["stages"][stage]["passages"]}
        assert ranks == best
        assert [i["rank"] for i in body["stages"][stage]["passages"]] == sorted(
            ranks.values()
        )


def test_rerank_scores_against_the_whole_question(
    split: TestClient, index: Callable[..., None]
) -> None:
    """The reranker scores the fused passages against the query before the split."""
    index(SEA, HARBOUR)
    reranker = RecordingReranker()
    split.app.state.reranker = reranker  # ty: ignore[unresolved-attribute]
    llm = script(split, reply("lamps and ships"), queries_reply("lamps", "ships"))
    llm.replies.append(reply(answer()))
    body = ask(split, "And the lamps?", turns=TURNS[:1])
    assert reranker.queries == ["lamps and ships"]
    assert body["search_query"] == "lamps and ships"
    rewrite, decompose, _ = llm.prompts
    assert isinstance(rewrite, RewritePrompt)
    # Decomposition splits the rewritten search query, not the question.
    assert isinstance(decompose, DecomposePrompt)
    assert decompose.query == "lamps and ships"


def test_decompose_call_counts_in_usage(
    split: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """The decompose call's tokens and cost are in `usage` and the usage log."""
    index(SEA)
    script(split, queries_reply("lamp", "ships"), reply(answer()))
    body = ask(split, "lamp and ships")
    assert body["usage"]["input_tokens"] == 200  # noqa: PLR2004
    assert body["usage"]["output_tokens"] == 20  # noqa: PLR2004
    assert body["usage"]["cost_usd"] == 0.5  # noqa: PLR2004
    [row] = usage_rows(engine)
    assert {key: row[key] for key in body["usage"]} == body["usage"]


@pytest.mark.parametrize(
    ("decompose_reply", "expected"),
    [
        pytest.param(reply("not json"), ["lamp and ships"], id="invalid"),
        pytest.param(queries_reply(), ["lamp and ships"], id="empty"),
        pytest.param(
            queries_reply("a", "b", "c", "d", "e"), ["a", "b", "c", "d"], id="too long"
        ),
        pytest.param(LlmError("overloaded"), ["lamp and ships"], id="provider error"),
    ],
)
def test_bad_decompose_reply_falls_back(
    split: TestClient,
    index: Callable[..., None],
    decompose_reply: Completion | Exception,
    expected: list[str],
) -> None:
    """A bad reply gives one query, or the first 4, and chat still answers."""
    index(SEA)
    general = {"kind": "general", "text": "Lamps guide ships.", "citations": []}
    script(split, decompose_reply, reply(answer(general)))
    body = ask(split, "lamp and ships")
    assert [q["text"] for q in body["retrieval"]["queries"]] == expected
    assert body["parts"] == [general]


def test_stream_done_carries_the_subquestions(
    split: TestClient, index: Callable[..., None]
) -> None:
    """The stream's `done` event has the same queries and `found_by` as chat."""
    index(SEA, HARBOUR)
    [done] = named(stream(split, SPLIT), "done")
    retrieval = done["retrieval"]
    assert [q["text"] for q in retrieval["queries"]] == SUBQUESTIONS
    check_found_by(retrieval)
    whole = ask(split, SPLIT)["retrieval"]["candidates"]
    by_id = {c["passage_id"]: c for c in whole}
    assert {c["passage_id"]: c for c in retrieval["candidates"]} == by_id


def test_search_decompose_uses_the_model(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Search splits with the request's model, or the default chat model."""
    index(SEA, HARBOUR)
    llm = ModelLlm()
    client.app.state.llm = llm  # ty: ignore[unresolved-attribute]
    body = search(client, SPLIT, decompose=True, model="openai/gpt-6.1-terra")
    assert [q["text"] for q in body["queries"]] == SUBQUESTIONS
    check_found_by(body)
    search(client, SPLIT, decompose=True)
    assert [(model, type(prompt)) for model, prompt in llm.calls] == [
        ("openai/gpt-6.1-terra", DecomposePrompt),
        ("anthropic/claude-sonnet-5-5", DecomposePrompt),
    ]


def test_search_without_decompose_makes_no_llm_call(
    split: TestClient, index: Callable[..., None]
) -> None:
    """Without `decompose`, search makes no LLM call, also with the switch on."""
    index(SEA)
    llm = script(split)
    body = search(split, SPLIT)
    assert llm.prompts == []
    [query] = body["queries"]
    assert (query["id"], query["text"]) == ("Q1", SPLIT)
    assert set(body) == {
        "query",
        "queries",
        "results",
        "stages",
        "settings",
        "candidates",
    }


def test_search_refuses_an_unknown_model(client: TestClient) -> None:
    """A model that is not a chat model gives 422."""
    response = client.post(
        SEARCH, json={"query": SPLIT, "decompose": True, "model": "acme/nope"}
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {
        "error": "model: 'acme/nope' is not one of the chat models"
    }
