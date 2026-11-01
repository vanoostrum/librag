# Copyright (C) 2026 Theo van Oostrum
"""Add the chat usage log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `chat_usage`."""
    op.create_table(
        "chat_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("error", sa.Text()),
    )


def downgrade() -> None:
    """Drop `chat_usage`."""
    op.drop_table("chat_usage")
