# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for the LibRag routes."""

import socket
import tomllib
from collections.abc import Iterator
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from librag.main import app, create_app
from librag.settings import Settings
from librag.worker import tick, utc_now

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_ALL_OK = {
    "status": "ok",
    "checks": {"qdrant": "ok", "database": "ok", "worker": "ok"},
}


def _beat(database_url: str, age: timedelta) -> None:
    """Run one worker tick, with a clock that is `age` behind."""
    engine = create_engine(database_url)
    tick(engine, "test-worker", clock=lambda: utc_now() - age)
    engine.dispose()


def _closed_port_url() -> str:
    """Return a local URL where nothing listens."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    """Return a test client for the routes that do not touch Qdrant."""
    with TestClient(create_app(Settings(database_url=database_url))) as client:
        yield client


@pytest.fixture
def ready_settings(qdrant_url: str, database_url: str) -> Settings:
    """Return settings with a real Qdrant and a migrated database."""
    return Settings(qdrant_url=qdrant_url, database_url=database_url)


def test_homepage_is_the_library(client: TestClient) -> None:
    """GET / returns the Library page; test_library.py checks its content."""
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "<title>Library · LibRag</title>" in response.text
    assert '<h1 class="page-title">Your library is empty</h1>' in response.text


def test_health(ready_settings: Settings) -> None:
    """GET /health is 200 when Qdrant, the database and the worker are ready."""
    _beat(ready_settings.database_url, timedelta(seconds=0))
    with TestClient(create_app(ready_settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-type"] == "application/json"
        assert response.json() == _ALL_OK


def test_health_without_heartbeat(ready_settings: Settings) -> None:
    """GET /health is 503 before the worker wrote its first heartbeat."""
    with TestClient(create_app(ready_settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {
            "status": "unavailable",
            "checks": {"qdrant": "ok", "database": "ok", "worker": "unavailable"},
        }


def test_health_with_stale_heartbeat(ready_settings: Settings) -> None:
    """GET /health is 503 when the last heartbeat is older than 30 seconds."""
    _beat(ready_settings.database_url, timedelta(seconds=31))
    with TestClient(create_app(ready_settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {
            "status": "unavailable",
            "checks": {"qdrant": "ok", "database": "ok", "worker": "unavailable"},
        }


def test_health_after_a_fresh_heartbeat(ready_settings: Settings) -> None:
    """GET /health is 200 again once a stale worker writes a new heartbeat."""
    _beat(ready_settings.database_url, timedelta(seconds=31))
    _beat(ready_settings.database_url, timedelta(seconds=0))
    with TestClient(create_app(ready_settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.OK
        assert response.json() == _ALL_OK


def test_health_with_qdrant_unreachable(database_url: str) -> None:
    """GET /health is 503 when Qdrant does not answer."""
    _beat(database_url, timedelta(seconds=0))
    settings = Settings(qdrant_url=_closed_port_url(), database_url=database_url)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {
            "status": "unavailable",
            "checks": {"qdrant": "unavailable", "database": "ok", "worker": "ok"},
        }


def test_health_with_database_unreachable(qdrant_url: str, tmp_path: Path) -> None:
    """GET /health is 503 when the database cannot be opened."""
    missing = f"sqlite:///{tmp_path / 'missing' / 'librag.db'}"
    settings = Settings(qdrant_url=qdrant_url, database_url=missing)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json() == {
            "status": "unavailable",
            "checks": {
                "qdrant": "ok",
                "database": "unavailable",
                "worker": "unavailable",
            },
        }


def test_version(client: TestClient) -> None:
    """GET /version returns the version declared in pyproject.toml."""
    expected = tomllib.loads(_PYPROJECT.read_text())["project"]["version"]
    response = client.get("/version")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"version": expected}


@pytest.mark.parametrize("path", _DOCS_PATHS)
def test_builtin_docs_are_disabled(client: TestClient, path: str) -> None:
    """FastAPI's built-in documentation routes are turned off."""
    response = client.get(path)
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_only_expected_routes_are_registered() -> None:
    """The application serves no routes besides these paths and methods."""
    routes = sorted(
        (route.path, method)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    )
    assert routes == [
        ("/", "GET"),
        ("/api/books", "GET"),
        ("/api/books", "POST"),
        ("/api/chat", "POST"),
        ("/api/config/models", "GET"),
        ("/api/rag/search", "POST"),
        ("/health", "GET"),
        ("/library/books", "GET"),
        ("/version", "GET"),
    ]
