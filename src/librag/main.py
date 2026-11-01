# Copyright (C) 2026 Theo van Oostrum
"""LibRag HTTP application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPStatus
from importlib.metadata import version as package_version
from typing import Annotated, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import create_engine
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from librag.books import BookConflictError, add_book, list_books
from librag.embeddings import make_embedder
from librag.epub import EpubError
from librag.health import check_database, check_qdrant, check_worker
from librag.index import qdrant_client
from librag.search import SearchRequest, search
from librag.settings import MAX_SEARCH_K, Settings

MEGABYTE = 1024 * 1024
# Room for the multipart boundaries and headers around the file.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

SearchK = Annotated[int | None, Field(ge=1, le=MAX_SEARCH_K)]


class SearchBody(BaseModel):
    """The body of `POST /api/rag/search`. Only `query` is required."""

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    top_k: SearchK = None
    dense_k: SearchK = None
    bm25_k: SearchK = None
    book_ids: list[str] = []
    authors: list[str] = []


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


async def upload_book(request: Request) -> JSONResponse:
    """Store an uploaded EPUB, add its book in queued and queue its job."""
    state = request.app.state
    limit = state.settings.max_upload_mb * MEGABYTE
    too_large = JSONResponse(
        {"error": f"The file is larger than {state.settings.max_upload_mb} MB"},
        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + MULTIPART_OVERHEAD_BYTES:
        return too_large
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        return JSONResponse(
            {"error": "Send the EPUB in the multipart field 'file'"},
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    data = await upload.read(limit + 1)
    if len(data) > limit:
        return too_large
    try:
        book = await run_in_threadpool(add_book, state.engine, state.settings, data)
    except EpubError as error:
        return JSONResponse(
            {"error": str(error)}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY
        )
    except BookConflictError as conflict:
        return JSONResponse(
            {"error": conflict.message, "book_id": conflict.book_id},
            status_code=HTTPStatus.CONFLICT,
        )
    return JSONResponse(book, status_code=HTTPStatus.ACCEPTED)


async def refuse_invalid_request(_request: Request, error: Exception) -> JSONResponse:
    """Return 422 with what is wrong in the body, in the API's `error` shape."""
    assert isinstance(error, RequestValidationError)  # noqa: S101 - FastAPI's contract
    first = error.errors()[0]
    # The location starts with "body"; a number in it is a list index or a position.
    field = ".".join(part for part in first["loc"][1:] if isinstance(part, str))
    return JSONResponse(
        {"error": f"{field}: {first['msg']}" if field else first["msg"]},
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return the LibRag app. Without `settings`, it reads them at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.settings = settings or Settings.from_env()
        app.state.engine = create_engine(app.state.settings.database_url)
        app.state.embedder = make_embedder(app.state.settings)
        app.state.qdrant = qdrant_client(app.state.settings.qdrant_url)
        yield
        app.state.qdrant.close()
        app.state.engine.dispose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, refuse_invalid_request)

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

    app.post("/api/books")(upload_book)

    @app.get("/api/books")
    def books(request: Request) -> dict[str, list[dict[str, object]]]:
        """List the books in the library, newest first."""
        return {"books": list_books(request.app.state.engine)}

    @app.post("/api/rag/search")
    def search_passages(body: SearchBody, request: Request) -> dict[str, Any]:
        """Return the passages that hybrid retrieval ranks highest, without the LLM."""
        state = request.app.state
        return search(
            state.engine,
            state.settings,
            state.embedder,
            state.qdrant,
            SearchRequest(**body.model_dump()),
        )

    @app.get("/version")
    def version() -> dict[str, str]:
        """Return the installed LibRag version, as declared in pyproject.toml."""
        return {"version": package_version("librag")}

    return app


app = create_app()
