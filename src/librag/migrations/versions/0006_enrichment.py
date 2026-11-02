# Copyright (C) 2026 Theo van Oostrum
"""Add contextual enrichment: the passages' context lines, the books' model and cost.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOK_COLUMNS = (
    "enrichment_cost_usd",
    "enrichment_output_tokens",
    "enrichment_input_tokens",
    "enrichment_model",
)


def upgrade() -> None:
    """Add `passages.context` and the enrichment columns of `books`.

    The books so far were indexed without enrichment: no model, no context
    lines, and nothing spent.
    """
    with op.batch_alter_table("passages") as batch:
        batch.add_column(sa.Column("context", sa.Text()))
    with op.batch_alter_table("books") as batch:
        batch.add_column(sa.Column("enrichment_model", sa.String(255)))
        for column in ("enrichment_input_tokens", "enrichment_output_tokens"):
            batch.add_column(
                sa.Column(column, sa.Integer(), nullable=False, server_default="0")
            )
        batch.add_column(
            sa.Column("enrichment_cost_usd", sa.Float(), server_default="0")
        )


def downgrade() -> None:
    """Drop the enrichment columns."""
    with op.batch_alter_table("books") as batch:
        for column in BOOK_COLUMNS:
            batch.drop_column(column)
    with op.batch_alter_table("passages") as batch:
        batch.drop_column("context")
