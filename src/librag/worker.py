# Copyright (C) 2026 Theo van Oostrum
"""The worker process. For now it only writes a heartbeat; it runs no jobs yet."""

import logging
import signal
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from types import FrameType

from sqlalchemy import Engine, create_engine, insert, update

from librag.db import to_db_time, worker_heartbeats
from librag.settings import Settings

HEARTBEAT_INTERVAL_SECONDS = 5.0

Clock = Callable[[], datetime]

logger = logging.getLogger("librag.worker")


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


def tick(engine: Engine, worker_id: str, clock: Clock = utc_now) -> None:
    """Write one heartbeat for `worker_id`, at the time `clock` gives."""
    beat_at = to_db_time(clock())
    with engine.begin() as connection:
        updated = connection.execute(
            update(worker_heartbeats)
            .where(worker_heartbeats.c.worker_id == worker_id)
            .values(beat_at=beat_at)
        )
        if updated.rowcount == 0:
            connection.execute(
                insert(worker_heartbeats).values(worker_id=worker_id, beat_at=beat_at)
            )


def run(engine: Engine, worker_id: str, stop: threading.Event) -> None:
    """Write a heartbeat every few seconds until `stop` is set."""
    while not stop.is_set():
        try:
            tick(engine, worker_id)
        except Exception:
            # A database outage must not stop the worker; the next tick retries.
            logger.exception("heartbeat failed")
        stop.wait(HEARTBEAT_INTERVAL_SECONDS)


def main() -> None:
    """Run the worker until it gets SIGTERM or SIGINT."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env()
    engine = create_engine(settings.database_url)
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("got %s, stopping", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = socket.gethostname()
    logger.info("worker %s started", worker_id)
    run(engine, worker_id, stop)
    engine.dispose()
    logger.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
