# Copyright (C) 2026 Theo van Oostrum
"""Reindex books: find the out-of-date ones, and queue the job that rebuilds each.

A book is out of date when its index configuration differs from the current
settings (ADR 0006). A change to the passage settings or the tokenizer needs a
new parse; a change to only the embedding model or the contextual enrichment
re-embeds the stored passages.
"""

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import Engine, RowMapping, select

from librag.books import (
    STATUS,
    BookNotFoundError,
    BookStateError,
    get_book,
    queue_job,
)
from librag.db import books
from librag.index import delete_book_points
from librag.passages import TOKENIZER
from librag.settings import Settings


@dataclass(frozen=True)
class OutOfDate:
    """Why a book is out of date, and whether a re-embed is enough to fix it."""

    reason: str
    reembed: bool


# A book's status and index configuration.
_CONFIG = select(
    books.c.id,
    STATUS.label("status"),
    books.c.passage_target_tokens,
    books.c.passage_overlap_tokens,
    books.c.tokenizer,
    books.c.embedding_model,
    books.c.enrichment_model,
)


def _model_name(model: str | None) -> str:
    """Return the model without its provider: `text-embedding-3-small`."""
    return "an unknown model" if model is None else model.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Models:
    """The models that index passages now: the embedder's, and the enricher's.

    `enrichment` is None when contextual enrichment is off.
    """

    embedding: str
    enrichment: str | None = None


def _enrichment_change(indexed: str | None, current: str | None) -> str | None:
    """Return how the book's enrichment differs from the current one, if it does."""
    if indexed == current:
        return None
    if indexed is None:
        return "indexed without enrichment"
    if current is None:
        return "indexed with enrichment"
    return f"enriched with {_model_name(indexed)}"


def _out_of_date(
    row: RowMapping, settings: Settings, models: Models
) -> OutOfDate | None:
    if row["passage_target_tokens"] != settings.passage_target_tokens:
        return OutOfDate(
            f"passages of {row['passage_target_tokens']} tokens", reembed=False
        )
    if row["passage_overlap_tokens"] != settings.passage_overlap_tokens:
        return OutOfDate(
            f"passage overlap of {row['passage_overlap_tokens']} tokens", reembed=False
        )
    if row["tokenizer"] != TOKENIZER:
        return OutOfDate(f"tokenized with {row['tokenizer']}", reembed=False)
    if row["embedding_model"] != models.embedding:
        return OutOfDate(
            f"indexed with {_model_name(row['embedding_model'])}", reembed=True
        )
    change = _enrichment_change(row["enrichment_model"], models.enrichment)
    return None if change is None else OutOfDate(change, reembed=True)


def out_of_date_books(
    engine: Engine, settings: Settings, models: Models
) -> dict[str, OutOfDate]:
    """Return the indexed books that are out of date, by book ID."""
    with engine.connect() as connection:
        rows = connection.execute(_CONFIG.where(STATUS == "indexed")).mappings().all()
    found = {row["id"]: _out_of_date(row, settings, models) for row in rows}
    return {book_id: reason for book_id, reason in found.items() if reason}


def reindex_book(
    engine: Engine,
    settings: Settings,
    client: QdrantClient,
    book_id: str,
    models: Models,
) -> dict[str, Any]:
    """Take the indexed book out of search and queue the job that rebuilds it.

    The job re-embeds the stored passages when only the embedding model or the
    enrichment is out of date, and parses the EPUB again otherwise, also when
    the book is up to date. Raises `BookNotFoundError` when there is no such book, and
    `BookStateError` when it is not indexed.
    """
    not_indexed = BookStateError("Only an indexed book can be reindexed")
    with engine.connect() as connection:
        row = (
            connection.execute(_CONFIG.where(books.c.id == book_id))
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise BookNotFoundError(book_id)
    if row["status"] != "indexed":
        raise not_indexed
    reason = _out_of_date(row, settings, models)
    delete_book_points(client, settings.qdrant_collection_prefix, book_id)
    with engine.begin() as connection:
        if connection.scalar(select(STATUS).where(books.c.id == book_id)) != "indexed":
            raise not_indexed  # pragma: no cover - the book changed since the check
        queue_job(
            connection,
            settings,
            book_id,
            kind="reembed" if reason and reason.reembed else "ingest",
        )
    return get_book(engine, book_id)


def reindex_out_of_date(
    engine: Engine, settings: Settings, client: QdrantClient, models: Models
) -> list[str]:
    """Queue a reindex of every out-of-date book, and return their IDs."""
    book_ids = list(out_of_date_books(engine, settings, models))
    for book_id in book_ids:
        reindex_book(engine, settings, client, book_id, models)
    return book_ids
