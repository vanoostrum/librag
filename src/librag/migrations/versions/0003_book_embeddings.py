# Copyright (C) 2026 Theo van Oostrum
"""Add the embedding configuration, tokens and cost to books.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the embedding columns to `books`."""
    with op.batch_alter_table("books") as batch:
        batch.add_column(sa.Column("embedding_model", sa.String(255)))
        batch.add_column(sa.Column("embedding_vector_size", sa.Integer()))
        batch.add_column(sa.Column("bm25_method", sa.String(64)))
        batch.add_column(
            sa.Column(
                "embedding_tokens", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch.add_column(
            sa.Column("embedding_cost_usd", sa.Float(), server_default="0")
        )


def downgrade() -> None:
    """Drop the embedding columns from `books`."""
    with op.batch_alter_table("books") as batch:
        for column in (
            "embedding_cost_usd",
            "embedding_tokens",
            "bm25_method",
            "embedding_vector_size",
            "embedding_model",
        ):
            batch.drop_column(column)
