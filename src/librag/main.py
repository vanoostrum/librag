# Copyright (C) 2026 Theo van Oostrum
"""LibRag HTTP application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPStatus
from importlib.metadata import version as package_version

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine

from librag.health import check_database, check_qdrant, check_worker
from librag.settings import Settings

HOMEPAGE_HTML = """\
<!DOCTYPE html>
<html>
  <head>
    <title>LibRag</title>
  </head>
  <body>
    <h1>LibRag</h1>
  </body>
</html>
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return the LibRag app. Without `settings`, it reads them at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.settings = settings or Settings.from_env()
        app.state.engine = create_engine(app.state.settings.database_url)
        yield
        app.state.engine.dispose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def homepage() -> str:
        """Return the LibRag homepage."""
        return HOMEPAGE_HTML

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        """Say whether Qdrant, the database and the worker are ready."""
        state = request.app.state
        checks = {
            "qdrant": check_qdrant(state.settings.qdrant_url),
            "database": check_database(state.engine),
            "worker": check_worker(state.engine),
        }
        ready = all(status == "ok" for status in checks.values())
        return JSONResponse(
            {"status": "ok" if ready else "unavailable", "checks": checks},
            status_code=HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
        )

    @app.get("/version")
    def version() -> dict[str, str]:
        """Return the installed LibRag version, as declared in pyproject.toml."""
        return {"version": package_version("librag")}

    return app


app = create_app()
