# Copyright (C) 2026 Theo van Oostrum
"""Talk to the running stack: upload and index books, and ask questions.

Every e2e test goes through these helpers, so a live run logs the usage of
each indexed book and chat request, and checks its cost cap before each
chat request.
"""

import json
import os
import time
from http import HTTPStatus
from typing import Any

import httpx2
import pytest

from tests.e2e.live import (
    LIVE,
    BudgetReachedError,
    ChatRecord,
    EmbeddingRecord,
    UsageLog,
    budget_usd,
)
from tests.epubs import FixtureBook, make_epub

BASE_URL = os.environ.get("LIBRAG_E2E_URL", "http://localhost:8000")
# The real embedder and LLMs take longer than the fakes.
INDEX_TIMEOUT_SECONDS = 300 if LIVE else 60
CHAT_TIMEOUT_SECONDS = 180.0 if LIVE else 30.0
BUDGET_USD = budget_usd(os.environ)
USAGE = UsageLog()

Event = tuple[str, dict[str, Any]]


def upload(book: FixtureBook) -> str:
    """Upload `book` as an EPUB and return its ID."""
    files = {"file": ("book.epub", make_epub(book), "application/epub+zip")}
    response = httpx2.post(f"{BASE_URL}/api/books", files=files, timeout=10.0)
    assert response.status_code == HTTPStatus.ACCEPTED, response.text
    assert response.json()["status"] == "queued"
    return str(response.json()["id"])


def wait_until_indexed(book_id: str) -> dict[str, Any]:
    """Wait until the book is indexed, log its embedding usage, and return it."""
    deadline = time.monotonic() + INDEX_TIMEOUT_SECONDS
    listed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        books = httpx2.get(f"{BASE_URL}/api/books", timeout=5.0).json()["books"]
        listed = next(b for b in books if b["id"] == book_id)
        if listed["status"] not in {"queued", "parsing", "indexing"}:
            break
        time.sleep(0.5)
    assert listed["status"] == "indexed", listed
    USAGE.add_embedding(
        EmbeddingRecord(
            book_id=book_id,
            title=str(listed["title"]),
            tokens=int(listed["embedding_tokens"]),
            cost_usd=listed["embedding_cost_usd"],
        )
    )
    return listed


def index(book: FixtureBook) -> dict[str, Any]:
    """Upload `book`, wait until it is indexed, and return it as listed."""
    return wait_until_indexed(upload(book))


def _check_budget() -> None:
    """Fail the test, before it sends a request, once a live run hits its cap."""
    if not LIVE:
        return
    try:
        USAGE.check_budget(BUDGET_USD)
    except BudgetReachedError as error:
        pytest.fail(str(error), pytrace=False)


def _log_chat(
    model: str, route: str, question: str, usage: dict[str, Any], parts: list[Any]
) -> None:
    USAGE.add_chat(
        ChatRecord(
            model=model,
            route=route,
            question=question,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=usage["cost_usd"],
            latency_ms=usage["latency_ms"],
            parts=parts,
        )
    )


def chat(model: str, question: str, book_ids: list[str]) -> dict[str, Any]:
    """Ask `POST /api/chat`, check it answered with 200, and return the body."""
    _check_budget()
    response = httpx2.post(
        f"{BASE_URL}/api/chat",
        json={"question": question, "book_ids": book_ids, "model": model},
        timeout=CHAT_TIMEOUT_SECONDS,
    )
    assert response.status_code == HTTPStatus.OK, response.text
    body = response.json()
    _log_chat(model, "chat", question, body["usage"], body["parts"])
    return body


def chat_stream(model: str, question: str, book_ids: list[str]) -> list[Event]:
    """Ask `POST /api/chat/stream` and return its server-sent events, in order."""
    _check_budget()
    response = httpx2.post(
        f"{BASE_URL}/api/chat/stream",
        json={"question": question, "book_ids": book_ids, "model": model},
        timeout=CHAT_TIMEOUT_SECONDS,
    )
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events: list[Event] = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    name, data = events[-1]
    if name == "done":
        parts = [part for event, part in events if event == "part"]
        _log_chat(model, "stream", question, data["usage"], parts)
    return events


def chat_models() -> list[str]:
    """Return the IDs of the models that `GET /api/config/models` lists."""
    try:
        response = httpx2.get(f"{BASE_URL}/api/config/models", timeout=5.0)
    except httpx2.HTTPError as error:
        msg = (
            f"tests/e2e needs a running stack at {BASE_URL} ({error}). Start one, "
            "or point LIBRAG_E2E_URL at it. See the project-verify skill."
        )
        raise RuntimeError(msg) from error
    assert response.status_code == HTTPStatus.OK, response.text
    return [model["id"] for model in response.json()["models"]]
