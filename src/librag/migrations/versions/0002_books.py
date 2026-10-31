# Copyright (C) 2026 Theo van Oostrum
"""Add the books, ingestion jobs and passages tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `books`, `ingestion_jobs` and `passages`."""
    op.create_table(
        "books",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text()),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("passages_indexed", sa.Integer(), nullable=False),
        sa.Column("passages_total", sa.Integer()),
        sa.Column("passage_target_tokens", sa.Integer(), nullable=False),
        sa.Column("passage_overlap_tokens", sa.Integer(), nullable=False),
        sa.Column("tokenizer", sa.String(64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("book_id", sa.String(16), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
    )
    op.create_index("ix_ingestion_jobs_status_id", "ingestion_jobs", ["status", "id"])
    op.create_table(
        "passages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("book_id", sa.String(16), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chapter_title", sa.Text(), nullable=False),
        sa.Column("section_title", sa.Text()),
        sa.Column("spine_index", sa.Integer(), nullable=False),
        sa.Column("first_paragraph", sa.Integer(), nullable=False),
        sa.Column("last_paragraph", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_passages_book_id_position",
        "passages",
        ["book_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    """Drop `passages`, `ingestion_jobs` and `books`."""
    op.drop_table("passages")
    op.drop_table("ingestion_jobs")
    op.drop_table("books")
