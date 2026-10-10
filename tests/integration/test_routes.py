# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for the LibRag routes."""

from http import HTTPStatus

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from librag.main import app

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.fixture
def client() -> TestClient:
    """Return a test client for the LibRag app."""
    return TestClient(app)


def test_homepage(client: TestClient) -> None:
    """GET / returns the LibRag HTML page."""
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].split(";", 1)[0] == "text/html"
    assert "<title>LibRag</title>" in response.text
    assert "<h1>LibRag</h1>" in response.text


def test_health(client: TestClient) -> None:
    """GET /health returns the ok status."""
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", _DOCS_PATHS)
def test_builtin_docs_are_disabled(client: TestClient, path: str) -> None:
    """FastAPI's built-in documentation routes are turned off."""
    response = client.get(path)
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_only_homepage_and_health_are_registered() -> None:
    """The application serves no routes besides / and /health."""
    paths = sorted(route.path for route in app.routes if isinstance(route, APIRoute))
    assert paths == ["/", "/health"]
