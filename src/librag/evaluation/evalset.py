# Copyright (C) 2026 Theo van Oostrum
"""The evaluation set: its books and questions, read from TOML, and quote matching.

A question names the evidence quotes that a good answer needs. Retrieval finds
a quote when a passage contains it, after case, whitespace and punctuation are
folded, so a quote still matches when the passage size changes.
"""

import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

QUESTION_TYPES = ("factual", "conceptual", "cross-book", "indirect", "negative")


class EvalSetError(ValueError):
    """The evaluation set is not valid. The message names the question or book."""


@dataclass(frozen=True)
class EvalBook:
    """A Project Gutenberg book of the set, by the key the questions use."""

    key: str
    gutenberg: int
    title: str


@dataclass(frozen=True)
class Evidence:
    """An evidence quote, and the key of the book it comes from."""

    book: str
    quote: str


@dataclass(frozen=True)
class Question:
    """A question of the set, its type, its evidence, and its search filters.

    `books` holds book keys; the run turns them into book IDs. `authors` goes
    to the search as it is.
    """

    id: str
    type: str
    question: str
    evidence: tuple[Evidence, ...]
    books: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalSet:
    """The books and questions of an evaluation set."""

    books: Mapping[str, EvalBook]
    questions: tuple[Question, ...]


def fold(text: str) -> str:
    """Return `text` with case, whitespace and punctuation folded.

    Every character that is not a letter or digit becomes a space, and runs of
    spaces become one, so "Don't—stop!" and "don t stop" match.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def contains(text: str, quote: str) -> bool:
    """Return whether `text` holds `quote`, on whole words, after folding both."""
    return f" {fold(quote)} " in f" {fold(text)} "


def _string(where: str, entry: Mapping[str, Any], name: str) -> str:
    value = entry.get(name)
    if value is None:
        msg = f"{where}: missing field '{name}'"
        raise EvalSetError(msg)
    if not isinstance(value, str) or not value.strip():
        msg = f"{where}: '{name}' must be a non-empty string"
        raise EvalSetError(msg)
    return value


def _strings(where: str, entry: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = entry.get(name, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        msg = f"{where}: '{name}' must be a list of non-empty strings"
        raise EvalSetError(msg)
    return tuple(str(item) for item in value)


def _books(raw: Any) -> dict[str, EvalBook]:  # noqa: ANN401 - TOML data
    if not isinstance(raw, dict) or not raw:
        msg = "the set needs a [books.<key>] table for each book"
        raise EvalSetError(msg)
    books: dict[str, EvalBook] = {}
    for key, entry in raw.items():
        where = f"book {key}"
        if not isinstance(entry, dict):
            msg = f"{where}: must be a table"
            raise EvalSetError(msg)
        number = entry.get("gutenberg")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            msg = f"{where}: 'gutenberg' must be a Project Gutenberg ebook number"
            raise EvalSetError(msg)
        books[key] = EvalBook(key, number, _string(where, entry, "title"))
    return books


def _evidence(
    where: str,
    kind: str,
    raw: Any,  # noqa: ANN401 - TOML data
    books: Mapping[str, EvalBook],
) -> list[Evidence]:
    if raw is None and kind == "negative":
        return []
    if raw is None:
        msg = f"{where}: missing field 'evidence'"
        raise EvalSetError(msg)
    if not isinstance(raw, list):
        msg = f"{where}: 'evidence' must be a list of {{ book, quote }} tables"
        raise EvalSetError(msg)
    evidence = []
    for item in raw:
        if not isinstance(item, dict):
            msg = f"{where}: 'evidence' must be a list of {{ book, quote }} tables"
            raise EvalSetError(msg)
        book = _string(f"{where} evidence", item, "book")
        if book not in books:
            msg = f"{where}: evidence names unknown book '{book}'"
            raise EvalSetError(msg)
        evidence.append(Evidence(book, _string(f"{where} evidence", item, "quote")))
    return evidence


def _question(entry: Any, books: Mapping[str, EvalBook]) -> Question:  # noqa: ANN401 - TOML data
    if not isinstance(entry, dict):
        msg = "each [[questions]] entry must be a table"
        raise EvalSetError(msg)
    raw_id = entry.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        msg = "a question has no 'id'"
        raise EvalSetError(msg)
    where = f"question {raw_id}"
    kind = _string(where, entry, "type")
    if kind not in QUESTION_TYPES:
        msg = f"{where}: unknown type '{kind}'; use one of {', '.join(QUESTION_TYPES)}"
        raise EvalSetError(msg)
    text = _string(where, entry, "question")
    evidence = _evidence(where, kind, entry.get("evidence"), books)
    if kind == "negative" and evidence:
        msg = f"{where}: a negative question has no evidence quotes"
        raise EvalSetError(msg)
    if kind != "negative" and not evidence:
        msg = f"{where}: a {kind} question needs at least one evidence quote"
        raise EvalSetError(msg)
    if kind == "cross-book" and len({e.book for e in evidence}) < 2:  # noqa: PLR2004
        msg = f"{where}: a cross-book question needs quotes from at least 2 books"
        raise EvalSetError(msg)
    filter_books = _strings(where, entry, "books")
    unknown = [key for key in filter_books if key not in books]
    if unknown:
        msg = f"{where}: 'books' names unknown book '{unknown[0]}'"
        raise EvalSetError(msg)
    return Question(
        id=raw_id,
        type=kind,
        question=text,
        evidence=tuple(evidence),
        books=filter_books,
        authors=_strings(where, entry, "authors"),
    )


def parse(data: Mapping[str, Any]) -> EvalSet:
    """Return the evaluation set in `data`, the parsed TOML.

    Raises `EvalSetError`, naming the question or book, for a missing field, an
    unknown type or book, a cross-book question with quotes from one book, or
    a negative question with quotes.
    """
    books = _books(data.get("books"))
    raw = data.get("questions")
    if not isinstance(raw, list) or not raw:
        msg = "the set needs at least one [[questions]] entry"
        raise EvalSetError(msg)
    questions: list[Question] = []
    for entry in raw:
        question = _question(entry, books)
        if any(q.id == question.id for q in questions):
            msg = f"question {question.id}: the ID is used twice"
            raise EvalSetError(msg)
        questions.append(question)
    return EvalSet(books, tuple(questions))


def load(path: Path) -> EvalSet:
    """Read and check the evaluation set in the TOML file at `path`."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        msg = f"{path} is not valid TOML: {error}"
        raise EvalSetError(msg) from None
    return parse(data)


def missing_quotes(
    evalset: EvalSet, passages: Mapping[str, Sequence[str]]
) -> list[tuple[str, Evidence]]:
    """Return each (question ID, quote) that no passage of its book contains.

    `passages` holds the passage texts of each book, by book key.
    """
    return [
        (question.id, evidence)
        for question in evalset.questions
        for evidence in question.evidence
        if not any(contains(text, evidence.quote) for text in passages[evidence.book])
    ]
