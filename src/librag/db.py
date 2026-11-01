# Copyright (C) 2026 Theo van Oostrum
"""The metadata database: its tables, and how to migrate it with Alembic."""

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

MIGRATIONS = Path(__file__).resolve().parent / "migrations"

metadata = MetaData()

# The last time each worker said it was alive. `beat_at` is naive UTC, because
# SQLite does not store a time zone.
worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_id", String(255), primary_key=True),
    Column("beat_at", DateTime(), nullable=False),
)

# One row per book in the library. `id` comes from the EPUB metadata (ADR 0006).
# The passage settings, the embedding model, its vector size and the BM25 method
# are the book's index configuration. The embedding tokens and cost add up over
# the batches of its indexing; the cost is null when LiteLLM does not know it.
books = Table(
    "books",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("title", Text(), nullable=False),
    Column("author", Text()),
    Column("content_sha256", String(64), nullable=False, unique=True),
    Column("status", String(16), nullable=False),
    Column("error", Text()),
    Column("passages_indexed", Integer(), nullable=False),
    Column("passages_total", Integer()),
    Column("passage_target_tokens", Integer(), nullable=False),
    Column("passage_overlap_tokens", Integer(), nullable=False),
    Column("tokenizer", String(64), nullable=False),
    Column("uploaded_at", DateTime(), nullable=False),
    Column("embedding_model", String(255)),
    Column("embedding_vector_size", Integer()),
    Column("bm25_method", String(64)),
    Column("embedding_tokens", Integer(), nullable=False, server_default="0"),
    Column("embedding_cost_usd", Float(), server_default="0"),
)

# The work queue that the worker polls. `status` is queued, running, done or failed.
ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,
    Column("id", Integer(), primary_key=True, autoincrement=True),
    Column("book_id", String(16), ForeignKey("books.id"), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(), nullable=False),
    Column("started_at", DateTime()),
    Column("finished_at", DateTime()),
    Index("ix_ingestion_jobs_status_id", "status", "id"),
)

# A book's passages, with their source locations. `id` derives from the book ID
# and `position` (ADR 0006).
passages = Table(
    "passages",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("book_id", String(16), ForeignKey("books.id"), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("text", Text(), nullable=False),
    Column("chapter_title", Text(), nullable=False),
    Column("section_title", Text()),
    Column("spine_index", Integer(), nullable=False),
    Column("first_paragraph", Integer(), nullable=False),
    Column("last_paragraph", Integer(), nullable=False),
    Index("ix_passages_book_id_position", "book_id", "position", unique=True),
)

# One row per chat request: the model, the search query, the tokens and cost of
# its LLM calls, and their time. `cost_usd` is null when LiteLLM does not know a
# price; `error` holds the provider's message when the request failed. The
# question and the answer are not saved.
chat_usage = Table(
    "chat_usage",
    metadata,
    Column("id", Integer(), primary_key=True, autoincrement=True),
    Column("created_at", DateTime(), nullable=False),
    Column("model", String(255), nullable=False),
    Column("search_query", Text(), nullable=False),
    Column("input_tokens", Integer(), nullable=False),
    Column("output_tokens", Integer(), nullable=False),
    Column("cost_usd", Float()),
    Column("latency_ms", Float(), nullable=False),
    Column("error", Text()),
)


def to_db_time(moment: datetime) -> datetime:
    """Return an aware time as the naive UTC time that the database stores."""
    return moment.astimezone(UTC).replace(tzinfo=None)


def alembic_config(database_url: str) -> Config:
    """Return the Alembic configuration for the database at `database_url`."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade(database_url: str) -> None:
    """Migrate the database at `database_url` to the latest schema."""
    command.upgrade(alembic_config(database_url), "head")
