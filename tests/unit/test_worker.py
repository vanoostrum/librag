# Copyright (C) 2026 Theo van Oostrum
"""The worker process stops cleanly on SIGTERM. No request can reach that case."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, select

from librag.db import worker_heartbeats

STARTUP_TIMEOUT_SECONDS = 10
STOP_TIMEOUT_SECONDS = 5


def test_worker_beats_and_stops_on_sigterm(database_url: str) -> None:
    """The worker writes a heartbeat, then exits 0 soon after SIGTERM."""
    env = {**os.environ, "LIBRAG_DATABASE_URL": database_url}
    worker = subprocess.Popen(
        [sys.executable, "-m", "librag.worker"], env=env, stderr=subprocess.PIPE
    )
    engine = create_engine(database_url)
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        beats: list[object] = []
        while not beats and time.monotonic() < deadline:
            with engine.connect() as connection:
                beats = list(connection.execute(select(worker_heartbeats)).all())
            time.sleep(0.1)
        assert beats, "the worker wrote no heartbeat"
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=STOP_TIMEOUT_SECONDS) == 0
    finally:
        worker.kill()
        engine.dispose()


def test_worker_keeps_running_without_database(tmp_path: Path) -> None:
    """A failed heartbeat does not stop the worker; it still stops on SIGTERM."""
    missing = f"sqlite:///{tmp_path / 'missing' / 'librag.db'}"
    env = {**os.environ, "LIBRAG_DATABASE_URL": missing}
    worker = subprocess.Popen(
        [sys.executable, "-m", "librag.worker"], env=env, stderr=subprocess.PIPE
    )
    try:
        stderr = worker.stderr
        assert stderr is not None
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if b"heartbeat failed" in stderr.readline():
                break
        assert worker.poll() is None, "the worker stopped after a failed heartbeat"
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=STOP_TIMEOUT_SECONDS) == 0
    finally:
        worker.kill()
