# Copyright (C) 2026 Theo van Oostrum
"""Add the worker heartbeat table.

Revision ID: 0001
Revises:
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `worker_heartbeats`."""
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(255), primary_key=True),
        sa.Column("beat_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Drop `worker_heartbeats`."""
    op.drop_table("worker_heartbeats")
