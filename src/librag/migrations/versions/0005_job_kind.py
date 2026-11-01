# Copyright (C) 2026 Theo van Oostrum
"""Add the kind of each ingestion job: a full ingestion, or a re-embed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `kind` to `ingestion_jobs`; the jobs so far are full ingestions."""
    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.add_column(
            sa.Column("kind", sa.String(16), nullable=False, server_default="ingest")
        )


def downgrade() -> None:
    """Drop `kind` from `ingestion_jobs`."""
    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.drop_column("kind")
