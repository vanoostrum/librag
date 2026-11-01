# Copyright (C) 2026 Theo van Oostrum
"""Fixtures for the route tests that upload and index books."""

import ipaddress
import socket
import uuid
from collections.abc import Callable, Iterator
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import Engine, create_engine

from librag.index import qdrant_client
from librag.main import create_app
from librag.settings import Settings
from librag.worker import run_one_job
from tests.epubs import FixtureBook, make_epub


@pytest.fixture
def qdrant(qdrant_url: str) -> Iterator[QdrantClient]:
    """Return a client for the test Qdrant."""
    client = qdrant_client(qdrant_url)
    yield client
    client.close()


@pytest.fixture
def settings(
    database_url: str, tmp_path: Path, qdrant_url: str, qdrant: QdrantClient
) -> Iterator[Settings]:
    """Return test settings: a migrated database, an empty file store and the fakes.

    Each test gets its own collection prefix in the test Qdrant, removed after it.
    """
    prefix = f"test_{uuid.uuid4().hex[:12]}"
    yield Settings(
        database_url=database_url,
        file_store_dir=str(tmp_path / "files"),
        qdrant_url=qdrant_url,
        ai_providers="fake",
        qdrant_collection_prefix=prefix,
    )
    for collection in qdrant.get_collections().collections:
        if collection.name.startswith(f"{prefix}_"):
            qdrant.delete_collection(collection.name)


@pytest.fixture
def collection(settings: Settings) -> str:
    """Return the name of the fake embedder's collection for this test."""
    return f"{settings.qdrant_collection_prefix}_fake"


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """Return an engine on the test database, as the worker has."""
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def work(engine: Engine, settings: Settings) -> Callable[[], bool]:
    """Return a function that runs one worker tick: the oldest queued job."""
    return lambda: run_one_job(engine, settings)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """Return a test client for the app with `settings`."""
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def index(client: TestClient, work: Callable[[], bool]) -> Callable[..., None]:
    """Return a function that uploads fixture books and indexes them."""

    def index(*fixtures: FixtureBook) -> None:
        for fixture in fixtures:
            files = {"file": ("book.epub", make_epub(fixture), "application/epub+zip")}
            response = client.post("/api/books", files=files)
            assert response.status_code == HTTPStatus.ACCEPTED, response.text
            assert work()

    return index


@pytest.fixture
def no_internet(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Refuse every socket connection that leaves this machine, and record it."""
    refused: list[object] = []
    connect = socket.socket.connect

    def local_only(sock: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else None
        if isinstance(host, str) and not ipaddress.ip_address(host).is_loopback:
            refused.append(address)
            msg = f"no external calls: {address}"
            raise ConnectionRefusedError(msg)
        connect(sock, address)  # ty: ignore[invalid-argument-type]

    monkeypatch.setattr(socket.socket, "connect", local_only)
    return refused
