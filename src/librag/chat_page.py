# Copyright (C) 2026 Theo van Oostrum
"""The Chat page: the models to pick, and the indexed books grouped by author."""

from dataclasses import dataclass
from itertools import groupby
from typing import Any

from librag.settings import Settings

UNKNOWN_AUTHOR = "Unknown author"


@dataclass(frozen=True)
class PickerBook:
    """A book in the book picker."""

    id: str
    title: str


@dataclass(frozen=True)
class Author:
    """An author in the book picker, with their indexed books."""

    name: str
    books: tuple[PickerBook, ...]


def _sort_key(text: str) -> str:
    return text.casefold()


def authors(books: list[dict[str, Any]]) -> list[Author]:
    """Return the indexed books by author, both sorted by name.

    Books that are in progress or failed are left out: chat cannot cite them.
    Books without an author come last.
    """
    indexed = sorted(
        (
            (book["author"] or UNKNOWN_AUTHOR, PickerBook(book["id"], book["title"]))
            for book in books
            if book["status"] == "indexed"
        ),
        key=lambda pair: (
            pair[0] == UNKNOWN_AUTHOR,
            _sort_key(pair[0]),
            _sort_key(pair[1].title),
        ),
    )
    return [
        Author(name, tuple(book for _, book in group))
        for name, group in groupby(indexed, key=lambda pair: pair[0])
    ]


def chat_context(books: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """Return what the Chat page template needs."""
    return {
        "nav": "chat",
        "authors": authors(books),
        "models": settings.chat_models,
        "default_model": settings.chat_default_model,
    }
