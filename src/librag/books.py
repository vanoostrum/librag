# Copyright (C) 2026 Theo van Oostrum
"""Add, list, delete and retry the books of the library, with their ingestion jobs."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import (
    Connection,
    Engine,
    RowMapping,
    and_,
    case,
    delete,
    exists,
    insert,
    literal_column,
    not_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from librag.db import books, ingestion_jobs, passages, to_db_time
from librag.epub import read_metadata
from librag.index import delete_book_points
from librag.passages import TOKENIZER
from librag.settings import Settings

IN_PROGRESS = ("queued", "parsing", "indexing")
INTERRUPTED = "indexing was interrupted"


@dataclass(frozen=True)
class BookConflictError(Exception):
    """The book, or the same file, is already in the library."""

    message: str
    book_id: str


@dataclass(frozen=True)
class BookNotFoundError(Exception):
    """No book in the library has this ID."""

    book_id: str


@dataclass(frozen=True)
class BookStateError(Exception):
    """The book is in a state that does not allow the action."""

    message: str


# A book is interrupted when it is in progress but no job is queued or running to
# finish it. The API shows it as failed, so the user can retry it.
_has_active_job = exists().where(
    ingestion_jobs.c.book_id == books.c.id,
    ingestion_jobs.c.status.in_(("queued", "running")),
)
_interrupted = and_(books.c.status.in_(IN_PROGRESS), not_(_has_active_job))
# The status and error that the API shows.
STATUS = case((_interrupted, "failed"), else_=books.c.status)
_ERROR = case((_interrupted, INTERRUPTED), else_=books.c.error)


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
        "embedding_tokens": row["embedding_tokens"],
        "embedding_cost_usd": row["embedding_cost_usd"],
        "uploaded_at": row["uploaded_at"].replace(tzinfo=UTC).isoformat(),
    }


_COLUMNS = (
    books.c.id,
    books.c.title,
    books.c.author,
    STATUS.label("status"),
    books.c.passages_indexed,
    books.c.passages_total,
    _ERROR.label("error"),
    books.c.embedding_tokens,
    books.c.embedding_cost_usd,
    books.c.uploaded_at,
)


def get_book(engine: Engine, book_id: str) -> dict[str, Any]:
    """Return the book `book_id` as the API shows it.

    Raises `BookNotFoundError` when there is no such book.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(select(*_COLUMNS).where(books.c.id == book_id))
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise BookNotFoundError(book_id)
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


def delete_book(
    engine: Engine, settings: Settings, client: QdrantClient, book_id: str
) -> None:
    """Delete the book, its points in every collection, passages, jobs and EPUB.

    Raises `BookNotFoundError` when there is no such book, and `BookStateError`
    while a job is queued or running for it.
    """
    in_progress = BookStateError("The book is queued or being indexed")
    if get_book(engine, book_id)["status"] in IN_PROGRESS:
        raise in_progress
    # The points go first: if Qdrant fails, the book is still there to delete again.
    delete_book_points(client, settings.qdrant_collection_prefix, book_id)
    with engine.begin() as connection:
        status = connection.scalar(select(STATUS).where(books.c.id == book_id))
        if status in IN_PROGRESS:
            raise in_progress  # pragma: no cover - a job was queued since the check
        connection.execute(delete(passages).where(passages.c.book_id == book_id))
        connection.execute(
            delete(ingestion_jobs).where(ingestion_jobs.c.book_id == book_id)
        )
        connection.execute(delete(books).where(books.c.id == book_id))
    book_path(settings.file_store_dir, book_id).unlink(missing_ok=True)


def queue_job(
    connection: Connection,
    settings: Settings,
    book_id: str,
    kind: str = "ingest",
) -> None:
    """Put the book back in `queued` under the current passage settings, with a job.

    The book shows as new until the job has run, and search leaves it out.
    """
    connection.execute(
        update(books)
        .where(books.c.id == book_id)
        .values(
            status="queued",
            error=None,
            passages_indexed=0,
            passages_total=None,
            passage_target_tokens=settings.passage_target_tokens,
            passage_overlap_tokens=settings.passage_overlap_tokens,
            tokenizer=TOKENIZER,
        )
    )
    connection.execute(
        insert(ingestion_jobs).values(
            book_id=book_id,
            status="queued",
            kind=kind,
            created_at=to_db_time(datetime.now(UTC)),
        )
    )


def retry_book(
    engine: Engine, settings: Settings, client: QdrantClient, book_id: str
) -> dict[str, Any]:
    """Run the full ingestion of a failed or interrupted book again.

    Raises `BookNotFoundError` when there is no such book, and `BookStateError`
    when the book is not failed or interrupted.
    """
    not_failed = BookStateError("Only a failed or interrupted book can be retried")
    if get_book(engine, book_id)["status"] != "failed":
        raise not_failed
    # A failed indexing can leave some points behind; the new passages may differ.
    delete_book_points(client, settings.qdrant_collection_prefix, book_id)
    with engine.begin() as connection:
        if connection.scalar(select(STATUS).where(books.c.id == book_id)) != "failed":
            raise not_failed  # pragma: no cover - a job was queued since the check
        queue_job(connection, settings, book_id)
    return get_book(engine, book_id)
