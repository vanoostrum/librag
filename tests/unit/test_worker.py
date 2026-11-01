# Copyright (C) 2026 Theo van Oostrum
"""The worker process: SIGTERM, outages and restarts. No request can reach these."""

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx2
from sqlalchemy import create_engine, select, update

from librag.books import add_book
from librag.db import books, ingestion_jobs, worker_heartbeats
from librag.settings import Settings
from tests.epubs import make_epub

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
    stderr = worker.stderr
    assert stderr is not None
    failed = threading.Event()

    def watch_log() -> None:
        # A thread reads the log, so a silent worker cannot block the test.
        for line in stderr:
            if b"heartbeat failed" in line:
                failed.set()

    threading.Thread(target=watch_log, daemon=True).start()
    try:
        assert failed.wait(STARTUP_TIMEOUT_SECONDS), "the worker logged no failure"
        assert worker.poll() is None, "the worker stopped after a failed heartbeat"
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=STOP_TIMEOUT_SECONDS) == 0
    finally:
        worker.kill()


def test_worker_runs_an_interrupted_job_on_start(
    database_url: str, tmp_path: Path, qdrant_url: str
) -> None:
    """A job left running by a stopped worker is indexed when a worker starts."""
    prefix = f"test_{uuid.uuid4().hex[:12]}"
    file_store_dir = str(tmp_path / "files")
    engine = create_engine(database_url)
    add_book(
        engine,
        Settings(database_url=database_url, file_store_dir=file_store_dir),
        make_epub(),
    )
    with engine.begin() as connection:
        connection.execute(update(ingestion_jobs).values(status="running"))
        connection.execute(update(books).values(status="parsing"))
    env = {
        **os.environ,
        "LIBRAG_DATABASE_URL": database_url,
        "LIBRAG_FILE_STORE_DIR": file_store_dir,
        "LIBRAG_QDRANT_URL": qdrant_url,
        "LIBRAG_AI_PROVIDERS": "fake",
        "LIBRAG_QDRANT_COLLECTION_PREFIX": prefix,
    }
    worker = subprocess.Popen(
        [sys.executable, "-m", "librag.worker"], env=env, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        status = "parsing"
        while status != "indexed" and time.monotonic() < deadline:
            with engine.connect() as connection:
                status = connection.scalar(select(books.c.status))
            time.sleep(0.1)
        assert status == "indexed", "the worker did not run the interrupted job"
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=STOP_TIMEOUT_SECONDS) == 0
    finally:
        worker.kill()
        engine.dispose()
        httpx2.delete(f"{qdrant_url}/collections/{prefix}_fake", timeout=5.0)
