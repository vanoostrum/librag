# Copyright (C) 2026 Theo van Oostrum
"""Readiness checks for Qdrant, the metadata database and the worker."""

from datetime import timedelta
from typing import Literal

import httpx2
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from librag.db import to_db_time, worker_heartbeats
from librag.worker import utc_now

WORKER_STALE_AFTER = timedelta(seconds=30)
QDRANT_TIMEOUT_SECONDS = 2.0

CheckStatus = Literal["ok", "unavailable"]


def check_qdrant(qdrant_url: str) -> CheckStatus:
    """Return ok when Qdrant answers its readiness probe."""
    try:
        response = httpx2.get(
            f"{qdrant_url.rstrip('/')}/readyz", timeout=QDRANT_TIMEOUT_SECONDS
        )
    except httpx2.HTTPError:
        return "unavailable"
    return "ok" if response.is_success else "unavailable"


def check_database(engine: Engine) -> CheckStatus:
    """Return ok when the metadata database answers a query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return "unavailable"
    return "ok"


def check_worker(engine: Engine) -> CheckStatus:
    """Return ok when a worker wrote a heartbeat less than 30 seconds ago."""
    try:
        with engine.connect() as connection:
            last_beat = connection.scalar(select(func.max(worker_heartbeats.c.beat_at)))
    except SQLAlchemyError:
        return "unavailable"
    if last_beat is None:
        return "unavailable"
    fresh = to_db_time(utc_now()) - last_beat < WORKER_STALE_AFTER
    return "ok" if fresh else "unavailable"
