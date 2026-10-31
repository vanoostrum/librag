# Copyright (C) 2026 Theo van Oostrum
"""Add a book to the library and queue its ingestion job, and list the books."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, RowMapping, insert, literal_column, select
from sqlalchemy.exc import IntegrityError

from librag.db import books, ingestion_jobs, to_db_time
from librag.epub import read_metadata
from librag.passages import TOKENIZER
from librag.settings import Settings


@dataclass(frozen=True)
class BookConflictError(Exception):
    """The book, or the same file, is already in the library."""

    message: str
    book_id: str


def book_path(file_store_dir: str, book_id: str) -> Path:
    """Return where the file store keeps the EPUB of `book_id`."""
    return Path(file_store_dir) / "books" / f"{book_id}.epub"


def _store(path: Path, data: bytes) -> None:
    """Write `data` to `path` in one step, so no reader sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(handle, "wb") as file:
        file.write(data)
    Path(temporary).replace(path)


def _conflict(engine: Engine, book_id: str, sha256: str) -> BookConflictError | None:
    """Return why the book cannot be added: the same file, or the same book ID."""
    with engine.connect() as connection:
        same_file = connection.scalar(
            select(books.c.id).where(books.c.content_sha256 == sha256)
        )
        same_id = connection.scalar(select(books.c.id).where(books.c.id == book_id))
    if same_file is not None:
        return BookConflictError("This file is already in the library", same_file)
    if same_id is not None:
        return BookConflictError(
            "A book with this ID is already in the library", same_id
        )
    return None  # pragma: no cover - the clashing row was deleted since


def add_book(engine: Engine, settings: Settings, data: bytes) -> dict[str, Any]:
    """Store the EPUB in `data`, add its book in `queued` and queue its job.

    Raises `EpubError` when the file is not a readable EPUB with a title, and
    `BookConflictError` when the book or the file is already in the library.
    """
    metadata = read_metadata(data)
    book_id = metadata.book_id
    sha256 = hashlib.sha256(data).hexdigest()
    now = to_db_time(datetime.now(UTC))
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(books).values(
                    id=book_id,
                    title=metadata.title,
                    author=metadata.author,
                    content_sha256=sha256,
                    status="queued",
                    passages_indexed=0,
                    passage_target_tokens=settings.passage_target_tokens,
                    passage_overlap_tokens=settings.passage_overlap_tokens,
                    tokenizer=TOKENIZER,
                    uploaded_at=now,
                )
            )
            connection.execute(
                insert(ingestion_jobs).values(
                    book_id=book_id, status="queued", created_at=now
                )
            )
            # A book or file already in the library fails the insert on its key,
            # before any file is written. The insert also holds the write lock,
            # so a parallel upload of the same book waits, then fails the same way.
            _store(book_path(settings.file_store_dir, book_id), data)
    except IntegrityError:
        conflict = _conflict(engine, book_id, sha256)
        if conflict is None:  # pragma: no cover - the clashing row was deleted
            raise
        raise conflict from None
    return get_book(engine, book_id)


def _json(row: RowMapping) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "status": row["status"],
        "passages_indexed": row["passages_indexed"],
        "passages_total": row["passages_total"],
        "error": row["error"],
        "uploaded_at": row["uploaded_at"].replace(tzinfo=UTC).isoformat(),
    }


_COLUMNS = (
    books.c.id,
    books.c.title,
    books.c.author,
    books.c.status,
    books.c.passages_indexed,
    books.c.passages_total,
    books.c.error,
    books.c.uploaded_at,
)


def get_book(engine: Engine, book_id: str) -> dict[str, Any]:
    """Return the book `book_id` as the API shows it."""
    with engine.connect() as connection:
        row = (
            connection.execute(select(*_COLUMNS).where(books.c.id == book_id))
            .mappings()
            .one()
        )
    return _json(row)


def list_books(engine: Engine) -> list[dict[str, Any]]:
    """Return all books as the API shows them, newest first."""
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(*_COLUMNS).order_by(
                    books.c.uploaded_at.desc(), literal_column("books.rowid").desc()
                )
            )
            .mappings()
            .all()
        )
    return [_json(row) for row in rows]
