# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for answering questions with POST /api/chat and GET /api/config/models."""

import dataclasses
import hashlib
import json
from collections.abc import Callable, Iterator
from http import HTTPStatus
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from librag.db import chat_usage
from librag.llm import Completion, LlmError
from librag.main import create_app
from librag.passages import count_tokens
from librag.prompts import NO_PASSAGE, AnswerPrompt, Prompt, RewritePrompt
from librag.settings import ChatModel, Settings
from tests.epubs import FixtureBook, FixtureChapter, paragraphs

CHAT = "/api/chat"
DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"


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
    "The lighthouse keeper logged every ship that passed the cape.",
    "Wild strawberries grew along the railway embankment.",
)
HARBOUR = _book(
    "urn:harbour",
    "Harbour Tales",
    "Ben Author",
    "The lighthouse beam swept across the harbour fog.",
    "A lighthouse keeper rowed out to the harbour wall.",
)
SEA_ID = _id("urn:sea")
HARBOUR_ID = _id("urn:harbour")


def ask(client: TestClient, question: str, **fields: object) -> dict[str, Any]:
    """Ask, check the response is 200, and return its body."""
    response = client.post(CHAT, json={"question": question, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    return response.json()


def context(client: TestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the context of a chat answer, in the order the prompt numbers it.

    It is the rerank stage cut to `top_k`: the fixture passages are short, so
    the token budget cuts none. The passages come from a search for each text.
    """
    retrieval = body["retrieval"]
    ranked = retrieval["stages"]["rerank"]["passages"][: retrieval["settings"]["top_k"]]
    response = client.post(
        "/api/rag/search", json={"query": body["search_query"], "top_k": 100}
    )
    assert response.status_code == HTTPStatus.OK, response.text
    passages = {result["passage_id"]: result for result in response.json()["results"]}
    return [passages[item["passage_id"]] for item in ranked]


def answer(*parts: dict[str, Any]) -> str:
    """Return an LLM reply in the JSON answer format, with these parts."""
    return json.dumps({"parts": list(parts)})


class ScriptedLlm:
    """An LLM that returns the scripted replies in turn, and records each prompt.

    A reply that is an exception is raised instead.
    """

    def __init__(self, *replies: Completion | Exception) -> None:
        """Return `replies` in this order, one per call."""
        self.replies = list(replies)
        self.prompts: list[Prompt] = []

    def complete(self, model: str, prompt: Prompt) -> Completion:  # noqa: ARG002
        """Record `prompt`, then return or raise the next reply."""
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def stream(self, model: str, prompt: Prompt) -> Iterator[str | Completion]:
        """Stream the next reply in chunks of 5 characters, then its completion."""
        reply = self.complete(model, prompt)
        for start in range(0, len(reply.text), 5):
            yield reply.text[start : start + 5]
        yield reply


def reply(text: str, cost_usd: float | None = 0.25) -> Completion:
    """Return a completion of `text` with 100 input and 10 output tokens."""
    return Completion(text, input_tokens=100, output_tokens=10, cost_usd=cost_usd)


def script(client: TestClient, *replies: Completion | Exception) -> ScriptedLlm:
    """Make the app answer with the scripted replies, and return the LLM."""
    llm = ScriptedLlm(*replies)
    client.app.state.llm = llm  # ty: ignore[unresolved-attribute]
    return llm


def usage_rows(engine: Engine) -> list[dict[str, Any]]:
    """Return the usage log, oldest first, without the IDs and times."""
    with engine.connect() as connection:
        rows = connection.execute(select(chat_usage).order_by(chat_usage.c.id))
        return [
            {k: v for k, v in row._asdict().items() if k not in {"id", "created_at"}}
            for row in rows
        ]


def test_answer_cites_passages_of_the_context(
    client: TestClient, index: Callable[..., None]
) -> None:
    """The answer's citations resolve to passages of the request's context."""
    index(SEA)
    body = ask(client, "lighthouse keeper")
    selected = context(client, body)
    assert body["question"] == body["search_query"] == "lighthouse keeper"
    assert body["model"] == DEFAULT_MODEL
    assert body["parts"] == [
        {
            "kind": "book",
            "text": "The fake LLM answers from the passages it cites.",
            "citations": [1, 2],
        },
        {
            "kind": "synthesis",
            "text": f"The fake LLM sums up {len(selected)} passages.",
            "citations": [],
        },
    ]
    fields = ("passage_id", "book_id", "title", "author", "chapter", "section", "text")
    assert body["citations"] == [
        {"n": n, **{key: passage[key] for key in fields}}
        for n, passage in enumerate(selected[:2], start=1)
    ]
    assert body["citations"][0]["title"] == "Sea Stories"
    assert body["retrieval"]["settings"]["top_k"] == 10  # noqa: PLR2004
    fusion = body["retrieval"]["stages"]["fusion"]["passages"]
    assert {c["passage_id"] for c in body["citations"]} <= {
        p["passage_id"] for p in fusion
    }


CANDIDATE_FIELDS = ("passage_id", "book_id", "title", "chapter", "section", "text")


def staged_ids(retrieval: dict[str, Any]) -> set[str]:
    """Return the IDs of the passages in any stage of `retrieval`."""
    return {
        passage["passage_id"]
        for stage in retrieval["stages"].values()
        for passage in stage["passages"]
    }


def test_retrieval_lists_the_candidates_and_the_context(
    client: TestClient, index: Callable[..., None]
) -> None:
    """`retrieval` has each candidate's book and text, and the context sent."""
    index(SEA, HARBOUR)
    llm = script(client, reply(answer()))
    body = ask(client, "lighthouse keeper")
    retrieval = body["retrieval"]
    [prompt] = llm.prompts
    assert isinstance(prompt, AnswerPrompt)
    sent = [passage["passage_id"] for passage in prompt.passages]
    assert sent
    assert retrieval["context"] == {
        "passage_ids": sent,
        "tokens": sum(count_tokens(passage["text"]) for passage in prompt.passages),
    }
    search = client.post(
        "/api/rag/search", json={"query": "lighthouse keeper", "top_k": 100}
    ).json()
    known = {result["passage_id"]: result for result in search["results"]}
    fused = [p["passage_id"] for p in retrieval["stages"]["fusion"]["passages"]]
    assert [c["passage_id"] for c in retrieval["candidates"]] == fused
    assert retrieval["candidates"] == [
        {key: known[passage][key] for key in CANDIDATE_FIELDS} for passage in fused
    ]


@pytest.fixture
def few_fused_client(settings: Settings) -> Iterator[TestClient]:
    """Return a test client for the app that fuses only 2 candidates."""
    few = dataclasses.replace(settings, fusion_top_k=2)
    with TestClient(create_app(few)) as client:
        yield client


def test_passages_outside_fusion_are_candidates_too(
    few_fused_client: TestClient, index: Callable[..., None]
) -> None:
    """A passage that only dense or BM25 found still has a candidate entry."""
    client = few_fused_client
    index(SEA, HARBOUR)
    retrieval = ask(client, "lighthouse keeper")["retrieval"]
    fused = [p["passage_id"] for p in retrieval["stages"]["fusion"]["passages"]]
    ids = [c["passage_id"] for c in retrieval["candidates"]]
    assert len(fused) == 2  # noqa: PLR2004
    assert ids[:2] == fused
    assert set(ids) == staged_ids(retrieval)
    assert len(ids) == len(set(ids)) == 5  # noqa: PLR2004
    assert {c["title"] for c in retrieval["candidates"]} == {
        "Sea Stories",
        "Harbour Tales",
    }


def test_empty_library_has_no_candidates(client: TestClient) -> None:
    """With no indexed book, there are no candidates and an empty context."""
    retrieval = ask(client, "lighthouse keeper")["retrieval"]
    assert retrieval["candidates"] == []
    assert retrieval["context"] == {"passage_ids": [], "tokens": 0}


def test_every_citation_number_resolves(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Each number in `parts` has one entry in `citations`, and only those."""
    index(SEA)
    script(
        client,
        reply(
            answer(
                {"kind": "book", "text": "Keeper.", "citations": [2]},
                {"kind": "book", "text": "Lamp.", "citations": [1, 2]},
                {"kind": "synthesis", "text": "Both.", "citations": [1]},
            )
        ),
    )
    body = ask(client, "lighthouse keeper")
    selected = context(client, body)
    # Numbered in the order the answer cites them: context 2 is cited first.
    assert [part["citations"] for part in body["parts"]] == [[1], [2, 1], [2]]
    assert [(c["n"], c["passage_id"]) for c in body["citations"]] == [
        (1, selected[1]["passage_id"]),
        (2, selected[0]["passage_id"]),
    ]


def test_citation_outside_the_context_is_removed(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A wrong number is dropped; a claim left without one moves to general."""
    index(SEA)
    script(
        client,
        reply(
            answer(
                {"kind": "book", "text": "Supported.", "citations": [1, 99]},
                {"kind": "book", "text": "Unsupported.", "citations": [0, 99]},
                {"kind": "general", "text": "Known.", "citations": [1]},
            )
        ),
    )
    body = ask(client, "lighthouse keeper")
    assert body["parts"] == [
        {"kind": "book", "text": "Supported.", "citations": [1]},
        {"kind": "general", "text": "Unsupported. Known.", "citations": []},
    ]
    assert [c["n"] for c in body["citations"]] == [1]


def test_library_without_indexed_books_answers_from_general_knowledge(
    client: TestClient,
) -> None:
    """With no passage in the context, the answer is one general part."""
    body = ask(client, "Who built the first lighthouse?")
    assert body["citations"] == []
    [part] = body["parts"]
    assert part["kind"] == "general"
    assert part["text"].startswith(NO_PASSAGE)
    assert part["citations"] == []


def test_empty_context_keeps_book_claims_out(client: TestClient) -> None:
    """Without passages, a book claim from the LLM still lands in general."""
    script(
        client,
        reply(answer({"kind": "book", "text": "Claimed.", "citations": [1]})),
    )
    body = ask(client, "lighthouse")
    assert body["parts"] == [
        {"kind": "general", "text": f"{NO_PASSAGE} Claimed.", "citations": []}
    ]


TURNS = [{"question": f"Question {n}?", "answer": f"Answer {n}."} for n in range(1, 6)]


def test_follow_up_is_rewritten_into_a_search_query(
    client: TestClient, index: Callable[..., None]
) -> None:
    """With turns, the LLM rewrites the question; its tokens count in the usage."""
    index(SEA)
    body = ask(client, "lighthouse keeper", turns=TURNS)
    assert body["search_query"] == "lighthouse keeper Question 5?"
    assert body["search_query"] != body["question"]

    llm = script(client, reply("brass lamp"), reply(answer()))
    body = ask(client, "And the lamp?", turns=TURNS)
    assert body["search_query"] == "brass lamp"
    assert body["usage"]["input_tokens"] == 200  # noqa: PLR2004
    assert body["usage"]["output_tokens"] == 20  # noqa: PLR2004
    assert body["usage"]["cost_usd"] == 0.5  # noqa: PLR2004
    rewrite, answered = llm.prompts
    assert isinstance(rewrite, RewritePrompt)
    assert isinstance(answered, AnswerPrompt)
    # Only the last 3 turns go to the LLM.
    assert [turn.question for turn in rewrite.turns] == [
        "Question 3?",
        "Question 4?",
        "Question 5?",
    ]
    assert answered.turns == rewrite.turns
    assert answered.question == "And the lamp?"


def test_question_without_turns_is_the_search_query(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Without turns, there is no rewrite."""
    index(SEA)
    llm = script(client, reply(answer()))
    body = ask(client, "lighthouse keeper")
    assert body["search_query"] == "lighthouse keeper"
    assert [type(prompt) for prompt in llm.prompts] == [AnswerPrompt]


def test_empty_rewrite_keeps_the_question(client: TestClient) -> None:
    """A rewrite with no text falls back to the question."""
    script(client, reply("  "), reply(answer()))
    body = ask(client, "lighthouse keeper", turns=TURNS[:1])
    assert body["search_query"] == "lighthouse keeper"


@pytest.fixture
def no_rewrite_client(settings: Settings) -> Iterator[TestClient]:
    """Return a test client for the app with query rewriting off."""
    off = dataclasses.replace(settings, query_rewrite=False)
    with TestClient(create_app(off)) as client:
        yield client


def test_rewrite_off_searches_the_question(no_rewrite_client: TestClient) -> None:
    """With LIBRAG_QUERY_REWRITE off, the search query is the question."""
    body = ask(no_rewrite_client, "lighthouse keeper", turns=TURNS)
    assert body["search_query"] == "lighthouse keeper"


def test_filters_limit_the_cited_passages(
    client: TestClient, index: Callable[..., None]
) -> None:
    """`book_ids` and `authors` limit the citations to those books and authors."""
    index(SEA, HARBOUR)
    both = ask(client, "polished brass lamp rowed harbour wall")
    assert {c["book_id"] for c in both["citations"]} == {SEA_ID, HARBOUR_ID}

    by_book = ask(client, "lighthouse keeper", book_ids=[HARBOUR_ID])
    assert by_book["citations"]
    assert {c["book_id"] for c in by_book["citations"]} == {HARBOUR_ID}

    by_author = ask(client, "lighthouse harbour", authors=["Ada Writer"])
    assert by_author["citations"]
    assert {c["author"] for c in by_author["citations"]} == {"Ada Writer"}


def test_each_request_is_logged(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """One usage row per request, with the values that `usage` shows."""
    index(SEA)
    first = ask(client, "lighthouse keeper")
    second = ask(
        client, "lighthouse keeper", turns=TURNS[:1], model="openai/gpt-6.1-terra"
    )
    rows = usage_rows(engine)
    assert rows == [
        {
            "model": body["model"],
            "search_query": body["search_query"],
            **body["usage"],
            "error": None,
        }
        for body in (first, second)
    ]
    assert rows[1]["model"] == "openai/gpt-6.1-terra"
    assert first["usage"]["input_tokens"] > 0
    assert first["usage"]["output_tokens"] > 0
    assert first["usage"]["cost_usd"] == 0.0
    assert first["usage"]["latency_ms"] >= 0.0


def test_unknown_price_gives_a_null_cost(client: TestClient, engine: Engine) -> None:
    """When LiteLLM does not know a price, the cost is null in the response and log."""
    script(client, reply("lighthouse", cost_usd=0.1), reply(answer(), cost_usd=None))
    body = ask(client, "lighthouse", turns=TURNS[:1])
    assert body["usage"]["cost_usd"] is None
    assert usage_rows(engine)[0]["cost_usd"] is None


def test_models_list_the_chat_models(client: TestClient) -> None:
    """GET /api/config/models lists Claude Sonnet 5.5 as the default, and Terra."""
    response = client.get("/api/config/models")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "models": [
            {"id": DEFAULT_MODEL, "name": "Claude Sonnet 5.5", "default": True},
            {"id": "openai/gpt-6.1-terra", "name": "GPT 6.1 Terra", "default": False},
        ]
    }


def test_configured_models_and_default(settings: Settings) -> None:
    """The models and the default come from the settings."""
    configured = dataclasses.replace(
        settings,
        chat_models=(ChatModel("a/one", "One"), ChatModel("b/two", "Two")),
        chat_default_model="b/two",
    )
    with TestClient(create_app(configured)) as client:
        models = client.get("/api/config/models").json()["models"]
        assert [(m["id"], m["default"]) for m in models] == [
            ("a/one", False),
            ("b/two", True),
        ]
        assert ask(client, "lighthouse")["model"] == "b/two"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"question": "x", "model": "openai/gpt-4"}, "model: 'openai/gpt-4'"),
        ({"question": ""}, "question: String should have at least 1 character"),
        ({"question": "   "}, "question: String should have at least 1 character"),
        ({}, "question: Field required"),
        ({"question": "x", "turns": [{"question": "y"}]}, "turns.answer: Field"),
    ],
)
def test_invalid_request_is_refused(
    client: TestClient, engine: Engine, body: dict[str, Any], error: str
) -> None:
    """An unknown model or an empty question returns 422, and is not logged."""
    response = client.post(CHAT, json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"].startswith(error), response.json()
    assert usage_rows(engine) == []


def test_provider_error_returns_502_and_is_logged(
    client: TestClient, engine: Engine
) -> None:
    """A provider error returns its message with 502, and the request is logged."""
    script(client, LlmError("AnthropicException - overloaded"))
    response = client.post(CHAT, json={"question": "lighthouse"})
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json() == {"error": "AnthropicException - overloaded"}
    [row] = usage_rows(engine)
    assert row["model"] == DEFAULT_MODEL
    assert row["search_query"] == "lighthouse"
    assert row["error"] == "AnthropicException - overloaded"
    assert (row["input_tokens"], row["output_tokens"]) == (0, 0)


def test_provider_error_in_the_rewrite_returns_502(
    client: TestClient, engine: Engine
) -> None:
    """A failing rewrite fails the request too."""
    script(client, LlmError("rate limited"))
    response = client.post(CHAT, json={"question": "lighthouse", "turns": TURNS})
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert usage_rows(engine)[0]["error"] == "rate limited"


def test_invalid_json_is_retried_once(client: TestClient, engine: Engine) -> None:
    """An answer that is not JSON is asked for again; both calls count."""
    llm = script(
        client,
        reply("Sure! Here is my answer."),
        reply(answer({"kind": "general", "text": "Known."})),
    )
    body = ask(client, "lighthouse")
    assert len(llm.prompts) == 2  # noqa: PLR2004
    assert body["usage"]["input_tokens"] == 200  # noqa: PLR2004
    assert body["parts"][0]["text"] == f"{NO_PASSAGE} Known."
    assert usage_rows(engine)[0]["error"] is None


def test_invalid_json_twice_returns_502(client: TestClient, engine: Engine) -> None:
    """A second invalid answer fails the request with 502, and it is logged."""
    llm = script(client, reply("not json"), reply('{"parts": "none"}'))
    response = client.post(CHAT, json={"question": "lighthouse"})
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json() == {
        "error": "The model's answer was not valid JSON, 2 times"
    }
    assert len(llm.prompts) == 2  # noqa: PLR2004
    [row] = usage_rows(engine)
    assert row["error"] == response.json()["error"]
    assert row["input_tokens"] == 200  # noqa: PLR2004


def test_fake_providers_call_no_external_api(
    client: TestClient, index: Callable[..., None], no_internet: list[object]
) -> None:
    """With LIBRAG_AI_PROVIDERS=fake, chat connects only to this machine."""
    index(SEA)
    body = ask(client, "lighthouse keeper", turns=TURNS)
    assert body["citations"]
    assert no_internet == []
