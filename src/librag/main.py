# Copyright (C) 2026 Theo van Oostrum
"""LibRag HTTP application."""

import json
from collections.abc import AsyncGenerator, Generator, Iterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from importlib.metadata import version as package_version
from typing import Annotated, Any, override

import anyio
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, StrictBool, StringConstraints
from sqlalchemy import create_engine
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from librag.books import (
    BookConflictError,
    BookNotFoundError,
    BookStateError,
    add_book,
    delete_book,
    list_books,
    retry_book,
)
from librag.chat import ChatError, ChatRequest, Event, chat, chat_stream
from librag.chat_page import chat_context
from librag.embeddings import make_embedder
from librag.epub import EpubError
from librag.health import check_database, check_qdrant, check_worker
from librag.index import qdrant_client
from librag.library import STATIC_DIR, TEMPLATES, library_context
from librag.llm import make_llm
from librag.prompts import Turn
from librag.reindex import out_of_date_books, reindex_book, reindex_out_of_date
from librag.rerank import make_reranker
from librag.search import Searcher, SearchRequest, search
from librag.settings import MAX_SEARCH_K, MAX_TOKEN_BUDGET, MIN_TOKEN_BUDGET, Settings

MEGABYTE = 1024 * 1024
# Room for the multipart boundaries and headers around the file.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

SearchK = Annotated[int | None, Field(ge=1, le=MAX_SEARCH_K)]
TokenBudget = Annotated[int | None, Field(ge=MIN_TOKEN_BUDGET, le=MAX_TOKEN_BUDGET)]


class SearchBody(BaseModel):
    """The body of `POST /api/rag/search`. Only `query` is required."""

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    top_k: SearchK = None
    dense_k: SearchK = None
    bm25_k: SearchK = None
    fusion_k: SearchK = None
    token_budget: TokenBudget = None
    rerank: StrictBool = True
    book_ids: list[str] = []
    authors: list[str] = []


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TurnBody(BaseModel):
    """An earlier question in the conversation, and the answer it got."""

    question: str
    answer: str


class ChatBody(BaseModel):
    """The body of `POST /api/chat`. Only `question` is required."""

    question: NonBlank
    turns: list[TurnBody] = []
    model: str | None = None
    book_ids: list[str] = []
    authors: list[str] = []


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


def _not_found(message: str = "No book with this ID") -> JSONResponse:
    return JSONResponse({"error": message}, status_code=HTTPStatus.NOT_FOUND)


REINDEX_OFF = "Reindexing is turned off"


def _conflict(error: BookStateError) -> JSONResponse:
    return JSONResponse({"error": error.message}, status_code=HTTPStatus.CONFLICT)


def remove_book(book_id: str, request: Request) -> Response:
    """Delete the book, its passages in every collection, its jobs and its EPUB."""
    state = request.app.state
    try:
        delete_book(state.engine, state.settings, state.qdrant, book_id)
    except BookNotFoundError:
        return _not_found()
    except BookStateError as error:
        return _conflict(error)
    return Response(status_code=HTTPStatus.NO_CONTENT)


def retry(book_id: str, request: Request) -> JSONResponse:
    """Run the full ingestion of a failed or interrupted book again."""
    state = request.app.state
    try:
        book = retry_book(state.engine, state.settings, state.qdrant, book_id)
    except BookNotFoundError:
        return _not_found()
    except BookStateError as error:
        return _conflict(error)
    return JSONResponse(book, status_code=HTTPStatus.ACCEPTED)


def reindex(book_id: str, request: Request) -> JSONResponse:
    """Rebuild an indexed book; only when LIBRAG_REINDEX_ENABLED is on."""
    state = request.app.state
    if not state.settings.reindex_enabled:
        return _not_found(REINDEX_OFF)
    try:
        book = reindex_book(
            state.engine, state.settings, state.qdrant, book_id, state.embedder.model
        )
    except BookNotFoundError:
        return _not_found()
    except BookStateError as error:
        return _conflict(error)
    return JSONResponse(book, status_code=HTTPStatus.ACCEPTED)


def reindex_all(request: Request) -> JSONResponse:
    """Reindex every out-of-date book; only when LIBRAG_REINDEX_ENABLED is on."""
    state = request.app.state
    if not state.settings.reindex_enabled:
        return _not_found(REINDEX_OFF)
    book_ids = reindex_out_of_date(
        state.engine, state.settings, state.qdrant, state.embedder.model
    )
    return JSONResponse({"book_ids": book_ids}, status_code=HTTPStatus.ACCEPTED)


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


def _chat_request(body: ChatBody, request: Request) -> ChatRequest | JSONResponse:
    """Return the chat request of `body`, or a 422 response for an unknown model."""
    settings = request.app.state.settings
    model = body.model or settings.chat_default_model
    if model not in {chat_model.id for chat_model in settings.chat_models}:
        return JSONResponse(
            {"error": f"model: {model!r} is not one of the chat models"},
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    return ChatRequest(
        question=body.question,
        model=model,
        turns=[Turn(turn.question, turn.answer) for turn in body.turns],
        book_ids=body.book_ids,
        authors=body.authors,
    )


def answer_question(body: ChatBody, request: Request) -> JSONResponse:
    """Answer the question from the library, with citations to its passages."""
    chat_request = _chat_request(body, request)
    if isinstance(chat_request, JSONResponse):
        return chat_request
    try:
        return JSONResponse(
            chat(_searcher(request), request.app.state.llm, chat_request)
        )
    except ChatError as error:
        return JSONResponse({"error": str(error)}, status_code=HTTPStatus.BAD_GATEWAY)


def _server_sent(events: Iterator[Event]) -> Iterator[str]:
    for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data)}\n\n"


class EventStream(StreamingResponse):
    """Server-sent events that are closed when the response ends.

    Starlette does not close a sync iterator when the client disconnects, so
    the events would wait for the garbage collector to log their usage.
    """

    def __init__(self, events: Generator[Event]) -> None:
        """Stream `events`, one server-sent event each."""
        self.events = events
        super().__init__(
            _server_sent(events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the events; close them however the response ends."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self.events.close)


def stream_answer(body: ChatBody, request: Request) -> Response:
    """Stream the answer as server-sent events, one checked part at a time."""
    chat_request = _chat_request(body, request)
    if isinstance(chat_request, JSONResponse):
        return chat_request
    return EventStream(
        chat_stream(_searcher(request), request.app.state.llm, chat_request)
    )


def list_chat_models(request: Request) -> dict[str, list[dict[str, object]]]:
    """List the models that chat can answer with, and which one is the default."""
    settings = request.app.state.settings
    return {
        "models": [
            {
                "id": model.id,
                "name": model.name,
                "default": model.id == settings.chat_default_model,
            }
            for model in settings.chat_models
        ]
    }


def _searcher(request: Request) -> Searcher:
    state = request.app.state
    return Searcher(
        engine=state.engine,
        settings=state.settings,
        embedder=state.embedder,
        reranker=state.reranker,
        client=state.qdrant,
    )


def _library_context(request: Request) -> dict[str, Any]:
    """Return what the library templates need: the books, and the out-of-date ones."""
    state = request.app.state
    out_of_date = (
        out_of_date_books(state.engine, state.settings, state.embedder.model)
        if state.settings.reindex_enabled
        else None
    )
    return library_context(list_books(state.engine), out_of_date)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return the LibRag app. Without `settings`, it reads them at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.settings = settings or Settings.from_env()
        app.state.engine = create_engine(app.state.settings.database_url)
        app.state.embedder = make_embedder(app.state.settings)
        app.state.reranker = make_reranker(app.state.settings)
        app.state.llm = make_llm(app.state.settings)
        app.state.qdrant = qdrant_client(app.state.settings.qdrant_url)
        yield
        app.state.qdrant.close()
        app.state.engine.dispose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, refuse_invalid_request)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def library_page(request: Request) -> HTMLResponse:
        """Return the Library page: the books, and the controls to add more."""
        state = request.app.state
        return TEMPLATES.TemplateResponse(
            request,
            "library.html",
            {
                **_library_context(request),
                "nav": "library",
                "max_upload_mb": state.settings.max_upload_mb,
            },
        )

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(request: Request) -> HTMLResponse:
        """Return the Chat page: the ask bar, the models and the book picker."""
        state = request.app.state
        return TEMPLATES.TemplateResponse(
            request,
            "chat.html",
            chat_context(list_books(state.engine), state.settings),
        )

    @app.get("/library/books", response_class=HTMLResponse)
    def library_books(request: Request) -> HTMLResponse:
        """Return the library region of the page, for the live refresh."""
        return TEMPLATES.TemplateResponse(
            request, "library_region.html", _library_context(request)
        )

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
        """Return the context that retrieval and reranking select, without the LLM."""
        return search(_searcher(request), SearchRequest(**body.model_dump()))

    app.post("/api/books/reindex-out-of-date")(reindex_all)
    app.delete("/api/books/{book_id}", response_model=None)(remove_book)
    app.post("/api/books/{book_id}/retry")(retry)
    app.post("/api/books/{book_id}/reindex")(reindex)
    app.post("/api/chat")(answer_question)
    app.post("/api/chat/stream", response_model=None)(stream_answer)
    app.get("/api/config/models")(list_chat_models)

    @app.get("/version")
    def version() -> dict[str, str]:
        """Return the installed LibRag version, as declared in pyproject.toml."""
        return {"version": package_version("librag")}

    return app


app = create_app()
