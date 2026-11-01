# Copyright (C) 2026 Theo van Oostrum
"""The evaluation's books on a running stack: download, upload, wait, delete.

The evaluation uses the normal stack. It records the books it uploads in
`uploaded.json` next to the EPUBs, and deletes only those, so a copy of an
evaluation book that was already in the library is never touched.
"""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

import httpx2

from librag.epub import read_metadata
from librag.evaluation.evalset import EvalBook, EvalSet

GUTENBERG_URL = "https://www.gutenberg.org"
UPLOADED = "uploaded.json"
POLL_SECONDS = 2.0
INDEX_TIMEOUT_SECONDS = 1800.0
Log = Callable[[str], None]


class EvalError(Exception):
    """The evaluation cannot go on. The message says why and what to do."""


def epub_path(books_dir: Path, book: EvalBook) -> Path:
    """Return where the EPUB of `book` is kept."""
    return books_dir / f"pg{book.gutenberg}.epub"


def download(gutenberg: httpx2.Client, book: EvalBook, path: Path) -> None:
    """Download the EPUB of `book` from Project Gutenberg to `path`."""
    url = f"/ebooks/{book.gutenberg}.epub3.images"
    try:
        response = gutenberg.get(url, follow_redirects=True, timeout=60.0)
    except httpx2.HTTPError as error:
        msg = f"could not download {book.title} from Project Gutenberg: {error}"
        raise EvalError(msg) from None
    if response.status_code != HTTPStatus.OK:
        msg = (
            f"could not download {book.title} from Project Gutenberg: "
            f"{response.status_code} for {response.url}"
        )
        raise EvalError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(response.content)
    partial.replace(path)


@dataclass
class Stack:
    """The running stack at `url`, through `http`, whose base URL is `url`."""

    http: httpx2.Client
    url: str
    wait: Callable[[float], None] = time.sleep
    log: Log = print
    index_timeout: float = INDEX_TIMEOUT_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:  # noqa: ANN401 - httpx2 keyword arguments
        try:
            return self.http.request(method, path, **kwargs)
        except httpx2.TransportError as error:
            msg = (
                f"the stack at {self.url} is not reachable ({error}). Start it with "
                "`docker compose up -d --wait`, or set LIBRAG_EVAL_URL to its URL."
            )
            raise EvalError(msg) from None

    @staticmethod
    def _check(response: httpx2.Response, what: str) -> None:
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            msg = f"{what} failed with {response.status_code}: {response.text}"
            raise EvalError(msg)

    def _json(self, response: httpx2.Response, what: str) -> Any:  # noqa: ANN401 - JSON
        self._check(response, what)
        return response.json()

    def books(self) -> list[dict[str, Any]]:
        """Return the books in the library, as `GET /api/books` lists them."""
        return self._json(self._request("GET", "/api/books"), "GET /api/books")["books"]

    def search(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Return the response body of `POST /api/rag/search` for `body`."""
        response = self._request("POST", "/api/rag/search", json=body)
        return self._json(response, "POST /api/rag/search")

    def upload(self, path: Path) -> str:
        """Upload the EPUB at `path` and return its book ID."""
        files = {"file": (path.name, path.read_bytes(), "application/epub+zip")}
        response = self._request("POST", "/api/books", files=files)
        return str(self._json(response, f"uploading {path.name}")["id"])

    def delete(self, book_id: str) -> None:
        """Delete the book `book_id`; a book that is already gone is fine."""
        response = self._request("DELETE", f"/api/books/{book_id}")
        if response.status_code != HTTPStatus.NOT_FOUND:
            self._check(response, f"deleting book {book_id}")


def _uploaded(books_dir: Path) -> dict[str, list[str]]:
    path = books_dir / UPLOADED
    if not path.exists():
        return {}
    return cast("dict[str, list[str]]", json.loads(path.read_text(encoding="utf-8")))


def _record(books_dir: Path, url: str, book_ids: list[str]) -> None:
    uploaded = _uploaded(books_dir)
    if book_ids:
        uploaded[url] = book_ids
    else:
        uploaded.pop(url, None)
    books_dir.mkdir(parents=True, exist_ok=True)
    (books_dir / UPLOADED).write_text(
        json.dumps(uploaded, indent=2) + "\n", encoding="utf-8"
    )


def ensure_books(
    stack: Stack,
    evalset: EvalSet,
    books_dir: Path,
    fetch: Callable[[EvalBook, Path], None],
) -> dict[str, dict[str, Any]]:
    """Make every book of the set indexed on the stack; return each, by key.

    A missing EPUB is fetched into `books_dir`, and a book that is not in the
    library is uploaded. Then this waits until every book is `indexed`.
    Raises `EvalError` when a book fails or does not get indexed in time.
    """
    ids: dict[str, str] = {}
    for key, book in evalset.books.items():
        path = epub_path(books_dir, book)
        if not path.exists():
            stack.log(f"downloading {book.title} (Project Gutenberg #{book.gutenberg})")
            fetch(book, path)
        ids[key] = read_metadata(path.read_bytes()).book_id
    library = {entry["id"] for entry in stack.books()}
    uploaded = _uploaded(books_dir).get(stack.url, [])
    for key, book in evalset.books.items():
        if ids[key] in library:
            stack.log(f"{book.title} is already in the library")
            continue
        stack.log(f"uploading {book.title}")
        stack.upload(epub_path(books_dir, book))
        uploaded = [*uploaded, ids[key]]
        _record(books_dir, stack.url, uploaded)
    return _wait_until_indexed(stack, evalset, ids)


def _wait_until_indexed(
    stack: Stack, evalset: EvalSet, ids: Mapping[str, str]
) -> dict[str, dict[str, Any]]:
    deadline = stack.clock() + stack.index_timeout
    while True:
        library = {entry["id"]: entry for entry in stack.books()}
        gone = [key for key, book_id in ids.items() if book_id not in library]
        if gone:
            msg = f"{evalset.books[gone[0]].title} is no longer in the library"
            raise EvalError(msg)
        found = {key: library[book_id] for key, book_id in ids.items()}
        for key, entry in found.items():
            title = evalset.books[key].title
            if entry["status"] == "failed":
                msg = (
                    f"{title} is not indexed: it failed with '{entry['error']}'. "
                    "Retry it in the Library, then run the evaluation again."
                )
                raise EvalError(msg)
        waiting = [key for key, entry in found.items() if entry["status"] != "indexed"]
        if not waiting:
            return found
        if stack.clock() >= deadline:
            titles = ", ".join(evalset.books[key].title for key in waiting)
            msg = (
                f"{titles} not indexed after {stack.index_timeout:.0f} seconds. "
                "Check that the worker runs."
            )
            raise EvalError(msg)
        stack.wait(POLL_SECONDS)


def delete_uploaded(stack: Stack, books_dir: Path) -> None:
    """Delete the books that the evaluation uploaded to this stack."""
    remaining = list(_uploaded(books_dir).get(stack.url, []))
    for book_id in list(remaining):
        stack.delete(book_id)
        remaining.remove(book_id)
        _record(books_dir, stack.url, remaining)
        stack.log(f"deleted evaluation book {book_id}")
