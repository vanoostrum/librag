# Copyright (C) 2026 Theo van Oostrum
"""The metadata database: its tables, and how to migrate it with Alembic."""

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, MetaData, String, Table

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
