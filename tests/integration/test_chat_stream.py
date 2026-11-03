# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for streaming answers with POST /api/chat/stream."""

import json
import re
import threading
from collections.abc import Callable, Generator, Iterator
from http import HTTPStatus
from typing import Any, override

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from librag.chat import ABORTED
from librag.llm import Completion, FakeLlm, LlmError
from librag.prompts import NO_PASSAGE, Prompt, RewritePrompt
from tests.integration.test_chat import (
    DEFAULT_MODEL,
    HARBOUR,
    HARBOUR_ID,
    SEA,
    TURNS,
    ScriptedLlm,
    answer,
    ask,
    context,
    reply,
    script,
    usage_rows,
)

STREAM = "/api/chat/stream"
# Seconds that a test LLM and client wait for each other, at most.
WAIT = 5

Event = tuple[str, dict[str, Any]]


def events(text: str) -> list[Event]:
    """Return the server-sent events in `text` as (name, data) pairs."""
    found = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        found.append((fields["event"], json.loads(fields["data"])))
    return found


def stream(client: TestClient, question: str, **fields: object) -> list[Event]:
    """Ask on the stream, check it is a 200 event stream, and return its events."""
    response = client.post(STREAM, json={"question": question, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return events(response.text)


def named(found: list[Event], name: str) -> list[dict[str, Any]]:
    """Return the data of the events called `name`."""
    return [data for event, data in found if event == name]


def test_stream_sends_status_parts_and_done_in_order(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Searching, writing with the passage count, the parts, then done."""
    index(SEA)
    found = stream(client, "lighthouse keeper")
    names = [name for name, _ in found]
    assert names == ["status", "status", "part", "part", "done"]
    [searching, writing] = named(found, "status")
    assert searching == {"step": "searching"}
    done = named(found, "done")[0]
    selected = context(client, done)
    assert writing == {"step": "writing", "passages": len(selected)}
    assert [(p["kind"], p["citations"]) for p in named(found, "part")] == [
        ("book", [1, 2]),
        ("synthesis", []),
    ]


def test_every_citation_in_a_part_is_one_of_its_sources(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Each part's numbers are in its sources, and each source is in the context."""
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
    found = stream(client, "lighthouse keeper")
    done = named(found, "done")[0]
    selected = {p["passage_id"]: p for p in context(client, done)}
    fields = ("book_id", "title", "author", "chapter", "section", "text")
    for part in named(found, "part"):
        assert [source["n"] for source in part["sources"]] == part["citations"]
        for source in part["sources"]:
            passage = selected[source["passage_id"]]
            assert {key: source[key] for key in fields} == {
                key: passage[key] for key in fields
            }
    assert [p["citations"] for p in named(found, "part")] == [[1], [2, 1], [2]]


REPLIES = [
    answer(
        {"kind": "book", "text": "Supported.", "citations": [1, 99]},
        {"kind": "synthesis", "text": "Sum.", "citations": [2]},
        {"kind": "book", "text": "Unsupported.", "citations": [0, 99]},
        {"kind": "general", "text": "Known.", "citations": [1]},
        {"kind": "book", "text": "Later.", "citations": [3, 1]},
    ),
    answer(
        {"kind": "general", "text": "First general.", "citations": []},
        {"kind": "book", "text": "Claim.", "citations": [2]},
    ),
    answer({"kind": "book", "text": "Only.", "citations": [7]}),
    "```json\n"
    + answer({"kind": "book", "text": "Fenced.", "citations": [1]})
    + "\n```",
]


@pytest.mark.parametrize("text", REPLIES)
def test_stream_parts_equal_the_chat_parts(
    client: TestClient, index: Callable[..., None], text: str
) -> None:
    """With the same reply, the stream's parts are the parts of POST /api/chat."""
    index(SEA)
    script(client, reply(text), reply(text))
    whole = ask(client, "lighthouse keeper")
    found = stream(client, "lighthouse keeper")
    parts = [
        {k: p[k] for k in ("kind", "text", "citations")} for p in named(found, "part")
    ]
    assert parts == whole["parts"]
    # Search can order passages with equal scores differently between requests,
    # so the cited passages are compared within the stream.
    done = named(found, "done")[0]
    assert [c["n"] for c in done["citations"]] == [c["n"] for c in whole["citations"]]
    cited = {
        source["n"]: source for p in named(found, "part") for source in p["sources"]
    }
    assert sorted(cited.values(), key=lambda s: s["n"]) == done["citations"]


def test_uncited_book_claim_arrives_in_general_knowledge(
    client: TestClient, index: Callable[..., None]
) -> None:
    """A book claim that loses all its citations is never sent as a book part."""
    index(SEA)
    script(
        client,
        reply(
            answer(
                {"kind": "book", "text": "Unsupported.", "citations": [99]},
                {"kind": "book", "text": "Supported.", "citations": [1]},
            )
        ),
    )
    parts = named(stream(client, "lighthouse keeper"), "part")
    assert [(p["kind"], p["text"]) for p in parts] == [
        ("book", "Supported."),
        ("general", "Unsupported."),
    ]
    assert parts[1]["citations"] == parts[1]["sources"] == []


class BreakingLlm(ScriptedLlm):
    """An LLM that streams `text`, then fails with a provider error."""

    def __init__(self, text: str, error: LlmError) -> None:
        """Stream `text`, then raise `error`."""
        super().__init__(reply(text))
        self.error = error

    @override
    def stream(self, model: str, prompt: Prompt) -> Iterator[str | Completion]:
        """Yield the text chunks of the reply, then raise instead of finishing."""
        for item in super().stream(model, prompt):
            if isinstance(item, Completion):
                raise self.error
            yield item


def test_book_claims_stream_before_the_reply_ends(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """A checked book claim is sent while the LLM still writes; held parts are not.

    The provider fails after two complete parts: the book claim was already
    sent, the synthesis was held for the end and is lost with the error.
    """
    index(SEA)
    text = answer(
        {"kind": "book", "text": "First.", "citations": [1]},
        {"kind": "synthesis", "text": "Sum.", "citations": []},
    )[:-2]
    client.app.state.llm = BreakingLlm(text, LlmError("connection reset"))  # ty: ignore[unresolved-attribute]
    found = stream(client, "lighthouse keeper")
    assert [name for name, _ in found] == ["status", "status", "part", "error"]
    assert named(found, "part")[0]["text"] == "First."
    assert named(found, "error") == [{"message": "connection reset"}]
    assert usage_rows(engine)[0]["error"] == "connection reset"


def test_done_carries_the_answer_details_and_the_stream_is_logged(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """`done` has what POST /api/chat returns besides the parts; one usage row."""
    index(SEA)
    script(client, reply("brass lamp"), reply(answer()))
    found = stream(client, "And the lamp?", turns=TURNS, model="openai/gpt-6.1-terra")
    done = named(found, "done")[0]
    assert done["question"] == "And the lamp?"
    assert done["search_query"] == "brass lamp"
    assert done["model"] == "openai/gpt-6.1-terra"
    assert done["citations"] == []
    assert set(done["retrieval"]) == {
        "queries",
        "stages",
        "settings",
        "candidates",
        "context",
    }
    assert {k: done["usage"][k] for k in ("input_tokens", "output_tokens")} == {
        "input_tokens": 200,
        "output_tokens": 20,
    }
    assert done["usage"]["cost_usd"] == 0.5  # noqa: PLR2004
    assert usage_rows(engine) == [
        {
            "model": "openai/gpt-6.1-terra",
            "search_query": "brass lamp",
            **done["usage"],
            "error": None,
        }
    ]


def test_empty_library_streams_one_general_part(client: TestClient) -> None:
    """With no passage, the stream sends 0 passages and one general part."""
    found = stream(client, "Who built the first lighthouse?")
    assert named(found, "status")[1] == {"step": "writing", "passages": 0}
    [part] = named(found, "part")
    assert part["kind"] == "general"
    assert part["text"].startswith(NO_PASSAGE)


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"question": "x", "model": "openai/gpt-4"}, "model: 'openai/gpt-4'"),
        ({"question": "  "}, "question: String should have at least 1 character"),
    ],
)
def test_invalid_request_is_refused_before_streaming(
    client: TestClient, engine: Engine, body: dict[str, Any], error: str
) -> None:
    """An unknown model or an empty question returns 422 JSON, not a stream."""
    response = client.post(STREAM, json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"].startswith(error)
    assert usage_rows(engine) == []


def test_provider_error_sends_an_error_event_and_is_logged(
    client: TestClient, engine: Engine
) -> None:
    """A provider error ends the stream with its message; the request is logged."""
    script(client, LlmError("RateLimitError - try again in a minute"))
    found = stream(client, "lighthouse")
    assert [name for name, _ in found] == ["status", "status", "error"]
    assert named(found, "error") == [
        {"message": "RateLimitError - try again in a minute"}
    ]
    [row] = usage_rows(engine)
    assert row["error"] == "RateLimitError - try again in a minute"


def test_provider_error_in_the_rewrite_sends_an_error_event(
    client: TestClient, engine: Engine
) -> None:
    """A failing rewrite ends the stream before the writing step."""
    script(client, LlmError("rate limited"))
    found = stream(client, "lighthouse", turns=TURNS)
    assert [name for name, _ in found] == ["status", "error"]
    assert usage_rows(engine)[0]["error"] == "rate limited"


def test_invalid_json_before_any_part_is_retried_once(
    client: TestClient, engine: Engine
) -> None:
    """An answer that is not JSON is asked for again; both calls count."""
    llm = script(
        client,
        reply("Sure! Here is my answer."),
        reply(answer({"kind": "general", "text": "Known."})),
    )
    found = stream(client, "lighthouse")
    assert len(llm.prompts) == 2  # noqa: PLR2004
    assert named(found, "part")[0]["text"] == f"{NO_PASSAGE} Known."
    assert named(found, "done")[0]["usage"]["input_tokens"] == 200  # noqa: PLR2004
    assert usage_rows(engine)[0]["error"] is None


def test_invalid_json_twice_sends_an_error_event(
    client: TestClient, engine: Engine
) -> None:
    """A second invalid answer ends the stream with an error, and is logged."""
    llm = script(client, reply("not json"), reply('{"parts": "none"}'))
    found = stream(client, "lighthouse")
    assert named(found, "error") == [
        {"message": "The model's answer was not valid JSON, 2 times"}
    ]
    assert len(llm.prompts) == 2  # noqa: PLR2004
    assert usage_rows(engine)[0]["input_tokens"] == 200  # noqa: PLR2004


def test_invalid_json_after_a_part_is_not_retried(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """Once a part is sent, a broken answer ends the stream instead of a retry."""
    index(SEA)
    first = answer({"kind": "book", "text": "Sent.", "citations": [1]})
    llm = script(client, reply(first[:-2] + ", oops"), reply(answer()))
    found = stream(client, "lighthouse keeper")
    assert [name for name, _ in found] == ["status", "status", "part", "error"]
    assert named(found, "error")[0]["message"].startswith("The model's answer")
    assert len(llm.prompts) == 1
    assert usage_rows(engine)[0]["error"] == named(found, "error")[0]["message"]


def test_book_ids_limit_the_cited_passages(
    client: TestClient, index: Callable[..., None]
) -> None:
    """`book_ids` limits the parts' sources to those books."""
    index(SEA, HARBOUR)
    found = stream(client, "lighthouse keeper", book_ids=[HARBOUR_ID])
    sources = [s for p in named(found, "part") for s in p["sources"]]
    assert sources
    assert {s["book_id"] for s in sources} == {HARBOUR_ID}


def test_default_model_is_used_without_one(client: TestClient) -> None:
    """Without `model`, the stream answers with the default model."""
    found = stream(client, "lighthouse")
    assert named(found, "done")[0]["model"] == DEFAULT_MODEL


def leave(client: TestClient, question: str, **fields: object) -> bytes:
    """Ask on the stream, and disconnect when the app's LLM is `waiting`.

    TestClient reads a response to its end, so this sends the request to the
    app as an ASGI server does. It sets the LLM's `left` event at the moment
    the client disconnects, and returns what the client got.
    """
    llm = client.app.state.llm  # ty: ignore[unresolved-attribute]
    body = json.dumps({"question": question, **fields}).encode()
    sent: list[dict[str, Any]] = []
    requests = [{"type": "http.request", "body": body, "more_body": False}]

    def got() -> bytes:
        return b"".join(m["body"] for m in sent if m["type"] == "http.response.body")

    async def receive() -> dict[str, Any]:
        if requests:
            return requests.pop()
        await anyio.to_thread.run_sync(llm.waiting.wait, WAIT)
        llm.left.set()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": STREAM,
        "raw_path": STREAM.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "state": {},
        "app": client.app,
    }
    client.portal.call(client.app, scope, receive, send)  # ty: ignore[unresolved-attribute]
    return got()


def words(text: str) -> int:
    """Return the tokens of `text` as the fake LLM counts them: its words."""
    return len(re.findall(r"\w+", text))


class StoppedLlm(FakeLlm):
    """A fake LLM whose answer the client stops after its first book claim.

    The answer is book claims of one chunk each. After the first one, it waits
    until the client has left; it then sends one more claim, the last one the
    server reads. It records the prompt, the text it sent, and whether the
    server closed its stream.
    """

    def __init__(self, cost_usd: float | None = 0.0) -> None:
        """Answer with a known price, or with None for a model without one."""
        self.waiting = threading.Event()
        self.left = threading.Event()
        self.cost_usd = cost_usd
        self.prompt: Prompt | None = None
        self.sent = ""
        self.closed = False

    @override
    def stream(self, model: str, prompt: Prompt) -> Generator[str | Completion]:
        """Yield one book claim per chunk; wait for the client after the first."""
        self.prompt = prompt
        claims = [
            json.dumps({"kind": "book", "text": f"Claim {n}.", "citations": [1]})
            for n in range(1, 10)
        ]
        chunks = ['{"parts": [' + claims[0], *[", " + c for c in claims[1:]], "]}"]
        try:
            for n, chunk in enumerate(chunks):
                if n == 1:
                    self.waiting.set()
                    self.left.wait(WAIT)
                self.sent += chunk
                yield chunk
        except GeneratorExit:
            self.closed = True
            raise
        yield self.complete(model, prompt)

    @override
    def estimate(self, model: str, prompt: Prompt, text: str) -> Completion:
        """Count as the fake LLM does, at this LLM's price."""
        estimate = super().estimate(model, prompt, text)
        return Completion(
            text, estimate.input_tokens, estimate.output_tokens, self.cost_usd
        )


def sent_words(prompt: Prompt | None) -> int:
    """Return the input tokens of `prompt` as the fake LLM counts them."""
    assert prompt is not None
    return words(" ".join(message["content"] for message in prompt.messages()))


def test_stopped_answer_is_logged_with_the_tokens_that_streamed(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """The client stops after a part: one row, with tokens for what streamed."""
    index(SEA)
    llm = StoppedLlm()
    client.app.state.llm = llm  # ty: ignore[unresolved-attribute]
    got = leave(client, "lighthouse keeper")
    assert b"Claim 1." in got
    assert b"event: done" not in got
    [row] = usage_rows(engine)
    assert row["error"] == ABORTED
    assert row["input_tokens"] == sent_words(llm.prompt) > 0
    assert row["output_tokens"] == words(llm.sent) > 0
    assert row["cost_usd"] == 0.0


def test_stopped_answer_closes_the_llm_stream(
    client: TestClient, index: Callable[..., None]
) -> None:
    """The server stops reading the LLM's stream when the client leaves."""
    index(SEA)
    llm = StoppedLlm()
    client.app.state.llm = llm  # ty: ignore[unresolved-attribute]
    leave(client, "lighthouse keeper")
    assert llm.closed
    assert "Claim 9." not in llm.sent


def test_stopped_answer_without_a_price_has_no_cost(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """A stopped request with a model that has no price logs its cost as None."""
    index(SEA)
    client.app.state.llm = StoppedLlm(cost_usd=None)  # ty: ignore[unresolved-attribute]
    leave(client, "lighthouse keeper")
    [row] = usage_rows(engine)
    assert row["error"] == ABORTED
    assert row["cost_usd"] is None


class SearchingLlm(FakeLlm):
    """A fake LLM whose rewrite waits until the client has left."""

    def __init__(self) -> None:
        """Record each completion."""
        self.waiting = threading.Event()
        self.left = threading.Event()
        self.completions: list[Completion] = []

    @override
    def complete(self, model: str, prompt: Prompt) -> Completion:
        """Wait for the client to leave in the rewrite, then answer as the fake."""
        if isinstance(prompt, RewritePrompt):
            self.waiting.set()
            self.left.wait(WAIT)
        completion = super().complete(model, prompt)
        self.completions.append(completion)
        return completion


def test_stream_the_client_leaves_while_searching_is_logged(
    client: TestClient, engine: Engine, index: Callable[..., None]
) -> None:
    """A client that leaves while searching: one row, with the rewrite's tokens."""
    index(SEA)
    llm = SearchingLlm()
    client.app.state.llm = llm  # ty: ignore[unresolved-attribute]
    got = leave(client, "lighthouse keeper", turns=TURNS)
    assert b"event: part" not in got
    [row] = usage_rows(engine)
    assert row["error"] == ABORTED
    assert row["search_query"] == llm.completions[0].text
    [rewrite] = llm.completions
    assert (row["input_tokens"], row["output_tokens"]) == (
        rewrite.input_tokens,
        rewrite.output_tokens,
    )
    assert row["input_tokens"] > 0


def test_done_carries_the_same_candidates_and_context_as_chat(
    client: TestClient, index: Callable[..., None]
) -> None:
    """`done` has the candidates and the context that POST /api/chat returns."""
    index(SEA, HARBOUR)
    script(client, reply(answer()), reply(answer()))
    whole = ask(client, "lighthouse keeper")["retrieval"]
    done = named(stream(client, "lighthouse keeper"), "done")[0]["retrieval"]
    # Equal scores can order passages differently between two requests.
    assert done["context"]["tokens"] == whole["context"]["tokens"]
    assert sorted(done["context"]["passage_ids"]) == sorted(
        whole["context"]["passage_ids"]
    )
    assert done["context"]["passage_ids"]
    by_id = {c["passage_id"]: c for c in whole["candidates"]}
    assert {c["passage_id"]: c for c in done["candidates"]} == by_id
