# Copyright (C) 2026 Theo van Oostrum
"""Chat: answer a question from the library's passages with an LLM, with citations.

The answer has three kinds of part: `book` claims, each citing context
passages, a `synthesis`, and `general` knowledge. The server checks each
citation against the context, so a claim never shows as coming from the books
without a passage that is in the context.
"""

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, insert

from librag.db import chat_usage, to_db_time
from librag.llm import Completion, Llm, LlmError
from librag.prompts import NO_PASSAGE, AnswerPrompt, Prompt, RewritePrompt, Turn
from librag.search import Searcher, SearchRequest, search

KINDS = ("book", "synthesis", "general")
# The rewrite and the answer see this many of the latest turns.
MAX_TURNS = 3
# Invalid JSON is asked for once more before the request fails.
ANSWER_ATTEMPTS = 2


@dataclass(frozen=True)
class Part:
    """One part of an answer, with the numbers of the passages it cites."""

    kind: str
    text: str
    citations: tuple[int, ...] = ()


class AnswerFormatError(ValueError):
    """The LLM's reply is not the JSON answer that the prompt asks for."""


def _strip_fence(text: str) -> str:
    """Return `text` without a Markdown code fence around it."""
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3]
        text = text.removeprefix("json")
    return text.strip()


def _part(item: object) -> Part:
    if not isinstance(item, dict):
        msg = "a part is not an object"
        raise AnswerFormatError(msg)
    kind, text, citations = (
        item.get("kind"),
        item.get("text"),
        item.get("citations", []),
    )
    if (
        kind not in KINDS
        or not isinstance(text, str)
        or not isinstance(citations, list)
    ):
        msg = "a part needs a known kind, a text and a list of citations"
        raise AnswerFormatError(msg)
    # A JSON true is a Python int; it is no citation number.
    numbers = tuple(
        n for n in citations if isinstance(n, int) and not isinstance(n, bool)
    )
    return Part(kind, text, numbers)


def parse_answer(text: str) -> list[Part]:
    """Return the parts of the LLM's JSON answer, or raise `AnswerFormatError`."""
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError as error:
        msg = f"the answer is not JSON: {error}"
        raise AnswerFormatError(msg) from error
    if not isinstance(data, dict) or not isinstance(data.get("parts"), list):
        msg = "the answer has no list of parts"
        raise AnswerFormatError(msg)
    return [_part(item) for item in data["parts"]]


FENCE = "```"
# The longest opening fence line that the reader waits through, "```json" plus space.
MAX_FENCE_INFO = 8
# A part object sits in the answer object's `parts` list: three levels deep.
PART_DEPTH = 3


class PartReader:
    """Find the complete parts in the LLM's JSON answer while it streams.

    `feed` returns each part as soon as its JSON object is complete. It reads
    early only a reply that starts with the answer object, after an optional
    `json` code fence; any other reply gives its parts at `finish`, which reads
    the whole reply with `parse_answer`.
    """

    def __init__(self) -> None:
        """Start with an empty reply."""
        self._text = ""
        self._pos = 0  # The next character to scan.
        self._scanning: bool | None = None  # None until the start is known.
        self._stack: list[str] = []
        self._in_string = False
        self._escape = False
        self._string_start = 0
        self._last_string = ""
        self._key = ""
        self._in_parts = False
        self._part_start = 0
        self._done = False
        self._parts: list[Part] = []

    def feed(self, chunk: str) -> list[Part]:
        """Add `chunk` to the reply; return the parts that it completes."""
        self._text += chunk
        if self._scanning is None:
            self._find_start()
        if self._scanning is not True:
            return []
        found: list[Part] = []
        while self._pos < len(self._text) and not self._done:
            part = self._scan(self._text[self._pos])
            self._pos += 1
            if part is not None:
                found.append(part)
        self._parts.extend(found)
        return found

    def finish(self) -> list[Part]:
        """Return the parts not returned yet, or raise `AnswerFormatError`."""
        parts = parse_answer(self._text)
        if parts[: len(self._parts)] != self._parts:
            msg = "the streamed parts differ from the whole answer"
            raise AnswerFormatError(msg)
        return parts[len(self._parts) :]

    def _find_start(self) -> None:
        text = self._text.lstrip()
        offset = len(self._text) - len(text)
        if not text:
            return
        if text.startswith("{"):
            self._scanning, self._pos = True, offset
            return
        if not text.startswith(FENCE[: len(text)]):
            self._scanning = False
            return
        info = text[len(FENCE) :]
        brace = info.find("{")
        if len(text) < len(FENCE) or (brace < 0 and len(info) <= MAX_FENCE_INFO):
            return
        if brace >= 0 and info[:brace].strip() in {"", "json"}:
            self._scanning = True
            self._pos = offset + len(FENCE) + brace
        else:
            self._scanning = False

    def _scan(self, char: str) -> Part | None:
        """Read one character of the answer object; return a part it completes."""
        if self._in_string:
            self._scan_string(char)
        elif char == '"':
            self._in_string, self._string_start = True, self._pos + 1
        elif char == ":" and len(self._stack) == 1:
            self._key = self._last_string
        elif char in "{[":
            self._open(char)
        elif char in "}]":
            return self._close(char)
        return None

    def _scan_string(self, char: str) -> None:
        if self._escape:
            self._escape = False
        elif char == "\\":
            self._escape = True
        elif char == '"':
            self._in_string = False
            self._last_string = self._text[self._string_start : self._pos]

    def _open(self, char: str) -> None:
        depth = len(self._stack)
        self._stack.append(char)
        if char == "[" and depth == 1 and self._key == "parts":
            self._in_parts = True
        elif char == "{" and depth == PART_DEPTH - 1 and self._in_parts:
            self._part_start = self._pos

    def _close(self, char: str) -> Part | None:
        depth = len(self._stack)
        self._stack.pop()
        self._done = not self._stack
        if char == "]" and depth == PART_DEPTH - 1:
            self._in_parts = False
        elif char == "}" and depth == PART_DEPTH and self._in_parts:
            return self._read_part(self._text[self._part_start : self._pos + 1])
        return None

    @staticmethod
    def _read_part(text: str) -> Part:
        try:
            return _part(json.loads(text))
        except json.JSONDecodeError as error:
            msg = f"a part is not JSON: {error}"
            raise AnswerFormatError(msg) from error


def _merged(kind: str, parts: Sequence[Part]) -> list[Part]:
    """Return `parts` as one part of `kind`, or no part when they have no text."""
    text = " ".join(part.text for part in parts)
    citations = tuple(dict.fromkeys(n for part in parts for n in part.citations))
    return [Part(kind, text, citations)] if text else []


def check_citations(parts: Sequence[Part], context_size: int) -> list[Part]:
    """Return the parts with only citations to the context's passages 1 to N.

    A book claim left without a citation moves into the general part, and the
    general part cites nothing. The parts come in the order book claims, one
    synthesis, one general part; a part without text is left out. With an
    empty context, the whole answer is one general part that starts with the
    no-passage sentence.
    """
    book: list[Part] = []
    synthesis: list[Part] = []
    general: list[Part] = []
    for part in parts:
        text = part.text.strip()
        valid = tuple(
            dict.fromkeys(n for n in part.citations if 1 <= n <= context_size)
        )
        if not text:
            continue
        if (
            not context_size
            or part.kind == "general"
            or (part.kind == "book" and not valid)
        ):
            general.append(Part("general", text))
        elif part.kind == "book":
            book.append(Part("book", text, valid))
        else:
            synthesis.append(Part("synthesis", text, valid))
    general_parts = _merged("general", general)
    if not context_size:
        text = general_parts[0].text if general_parts else ""
        if not text.startswith(NO_PASSAGE):
            text = f"{NO_PASSAGE} {text}".strip()
        general_parts = [Part("general", text)]
    return [*book, *_merged("synthesis", synthesis), *general_parts]


def number_citations(
    parts: Sequence[Part], context: Sequence[Mapping[str, Any]]
) -> tuple[list[Part], list[dict[str, Any]]]:
    """Renumber the cited passages 1, 2, … in the order the answer cites them.

    Return the parts with the new numbers, and the cited passages. `context`
    holds the passages that the context numbers 1 to N point to.
    """
    numbers: dict[int, int] = {}
    for part in parts:
        for n in part.citations:
            numbers.setdefault(n, len(numbers) + 1)
    renumbered = [
        Part(part.kind, part.text, tuple(numbers[n] for n in part.citations))
        for part in parts
    ]
    citations = [
        {
            "n": new,
            **{
                key: context[old - 1][key]
                for key in (
                    "passage_id",
                    "book_id",
                    "title",
                    "author",
                    "chapter",
                    "section",
                    "text",
                )
            },
        }
        for old, new in numbers.items()
    ]
    return renumbered, citations


@dataclass(frozen=True)
class ChatRequest:
    """A question, the conversation before it, the model, and the search filters."""

    question: str
    model: str
    turns: Sequence[Turn] = ()
    book_ids: Sequence[str] = ()
    authors: Sequence[str] = ()


class ChatError(Exception):
    """The LLM failed, or kept replying with an answer that is not valid JSON."""


@dataclass
class _Usage:
    """The tokens, cost and time of the LLM calls of one chat request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    latency_ms: float = 0.0

    def call(self, llm: Llm, model: str, prompt: Prompt) -> Completion:
        start = time.perf_counter()
        try:
            completion = llm.complete(model, prompt)
        finally:
            self.latency_ms += (time.perf_counter() - start) * 1000
        self.input_tokens += completion.input_tokens
        self.output_tokens += completion.output_tokens
        # One call without a known price makes the total unknown.
        if self.cost_usd is not None and completion.cost_usd is not None:
            self.cost_usd += completion.cost_usd
        else:
            self.cost_usd = None
        return completion

    def body(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": round(self.latency_ms, 3),
        }


def _log(
    engine: Engine, model: str, search_query: str, usage: _Usage, error: str | None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(chat_usage).values(
                created_at=to_db_time(datetime.now(UTC)),
                model=model,
                search_query=search_query,
                error=error,
                **usage.body(),
            )
        )


def _answer(llm: Llm, model: str, prompt: AnswerPrompt, usage: _Usage) -> list[Part]:
    for _ in range(ANSWER_ATTEMPTS):
        try:
            return parse_answer(usage.call(llm, model, prompt).text)
        except AnswerFormatError:
            continue
    msg = f"The model's answer was not valid JSON, {ANSWER_ATTEMPTS} times"
    raise ChatError(msg)


def chat(searcher: Searcher, llm: Llm, request: ChatRequest) -> dict[str, Any]:
    """Answer `request` from the context that search selects, and log its usage.

    With earlier turns and rewriting on, the LLM first rewrites the question
    into a standalone search query. Raise `ChatError` when the LLM fails; the
    request is logged either way.
    """
    settings = searcher.settings
    turns = tuple(request.turns[-MAX_TURNS:])
    usage = _Usage()
    search_query = request.question
    try:
        if turns and settings.query_rewrite:
            rewrite = RewritePrompt(request.question, turns)
            search_query = usage.call(llm, request.model, rewrite).text.strip()
            search_query = search_query or request.question
        retrieval = search(
            searcher,
            SearchRequest(
                query=search_query, book_ids=request.book_ids, authors=request.authors
            ),
        )
        context = retrieval["results"]
        prompt = AnswerPrompt(request.question, context, turns)
        parts = _answer(llm, request.model, prompt, usage)
    except (LlmError, ChatError) as error:
        _log(searcher.engine, request.model, search_query, usage, str(error))
        raise ChatError(str(error)) from error
    _log(searcher.engine, request.model, search_query, usage, None)
    parts, citations = number_citations(check_citations(parts, len(context)), context)
    return {
        "question": request.question,
        "search_query": search_query,
        "model": request.model,
        "parts": [
            {"kind": part.kind, "text": part.text, "citations": list(part.citations)}
            for part in parts
        ],
        "citations": citations,
        "usage": usage.body(),
        "retrieval": {
            "stages": retrieval["stages"],
            "settings": retrieval["settings"],
        },
    }
