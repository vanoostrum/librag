# Copyright (C) 2026 Theo van Oostrum
"""The Library page: the books as cards, with their status and progress.

`static/htmx.min.js` is htmx 2.0.11 (0BSD), copied from the npm package
`htmx.org`, `dist/htmx.min.js`; npm integrity `sha512-Thx/WtpeOQqSrqBCw/A1cwGJ…`.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.templating import Jinja2Templates

from librag.books import IN_PROGRESS
from librag.reindex import OutOfDate

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
STATIC_DIR = Path(__file__).parent / "static"

COVERS = ("slate", "clay", "ink", "olive")
_NUMBER_WORDS = (
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
)


@dataclass(frozen=True)
class Card:
    """What a book card shows.

    `note` says why the book is out of date. `actions` are the links under the
    status, of `retry`, `reindex` and `delete`.
    """

    book_id: str
    title: str
    author: str
    cover: str
    status: str
    status_text: str
    progress: int | None
    note: str | None
    actions: tuple[str, ...]


def _percent(book: dict[str, Any]) -> int:
    # The total is None until the worker has parsed the book.
    total = int(book["passages_total"] or 0)
    return int(book["passages_indexed"]) * 100 // total if total else 0


def _status_text(book: dict[str, Any]) -> str:
    match book["status"]:
        case "queued":
            return "Waiting in the queue"
        case "parsing":
            return "Reading the book"
        case "indexing":
            return f"Indexing · {_percent(book)}%"
        case "indexed":
            total = book["passages_total"]
            return f"Indexed · {total} passage{'' if total == 1 else 's'}"
        case _:
            return f"Failed: {book['error']}"


def _cover(book: dict[str, Any]) -> str:
    if book["status"] == "failed":
        return "blank"
    digest = hashlib.sha256(book["id"].encode()).digest()
    return COVERS[digest[0] % len(COVERS)]


def _actions(status: str, *, reindex_enabled: bool) -> tuple[str, ...]:
    # A book in progress has no actions, so a delete never meets a running job.
    match status:
        case "indexed":
            return ("reindex", "delete") if reindex_enabled else ("delete",)
        case "failed":
            return ("retry", "delete")
        case _:
            return ()


def card(book: dict[str, Any], out_of_date: dict[str, OutOfDate] | None) -> Card:
    """Return the card of `book`, as the API shows it.

    `out_of_date` holds the out-of-date books, or is None when the reindex
    switch is off.
    """
    reason = (out_of_date or {}).get(book["id"])
    return Card(
        book_id=book["id"],
        title=book["title"],
        author=book["author"] or "Unknown author",
        cover=_cover(book),
        status=book["status"],
        status_text=_status_text(book),
        progress=_percent(book) if book["status"] == "indexing" else None,
        note=f"Out of date: {reason.reason}" if reason else None,
        actions=_actions(book["status"], reindex_enabled=out_of_date is not None),
    )


def lede(count: int) -> str:
    """Return the line under the heading for a library of `count` books."""
    number = _NUMBER_WORDS[count - 1] if count <= len(_NUMBER_WORDS) else str(count)
    noun = "book" if count == 1 else "books"
    return f"{number} {noun}. Ask about any of them in Chat once they are indexed."


def library_context(
    books: list[dict[str, Any]], out_of_date: dict[str, OutOfDate] | None = None
) -> dict[str, Any]:
    """Return what the library templates need for `books`, newest first.

    `out_of_date` holds the out-of-date books, or is None when the reindex
    switch is off.
    """
    count = len(out_of_date or {})
    return {
        "cards": [card(book, out_of_date) for book in books],
        "reindex_label": (
            f"Reindex {count} out-of-date book{'' if count == 1 else 's'}"
            if count
            else None
        ),
        "lede": lede(len(books)) if books else None,
        "polling": any(book["status"] in IN_PROGRESS for book in books),
    }
