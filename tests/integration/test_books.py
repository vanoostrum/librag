# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for uploading books with POST /api/books and listing them with GET."""

import hashlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, create_engine, func, select, update

from librag.db import books, ingestion_jobs, passages
from librag.main import create_app
from librag.settings import Settings
from librag.worker import requeue_interrupted_jobs, run_one_job
from tests.epubs import (
    FixtureBook,
    FixtureChapter,
    make_epub,
    paragraphs,
    replace_member,
)

BOOK_ID = hashlib.sha256(b"urn:uuid:5f0c7c6e-0000-4000-8000-000000000001").hexdigest()[
    :16
]
TWO_CHAPTERS = FixtureBook(
    chapters=(
        FixtureChapter(paragraphs("First chapter text."), nav_title="One"),
        FixtureChapter(paragraphs("Second chapter text."), nav_title="Two"),
    )
)


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    """Return settings with a migrated database and an empty file store."""
    return Settings(database_url=database_url, file_store_dir=str(tmp_path / "files"))


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


def upload(client: TestClient, data: bytes, name: str = "book.epub") -> Response:
    """Upload `data` as the multipart field `file`."""
    files = {"file": (name, data, "application/epub+zip")}
    return client.post("/api/books", files=files)


def count(engine: Engine, table: Any) -> int:  # noqa: ANN401 - any SQLAlchemy table
    """Return the number of rows in `table`."""
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table)) or 0


def book_json(response_book: dict[str, Any], **expected: object) -> dict[str, Any]:
    """Return the expected book body, with the server's `uploaded_at`."""
    return {
        "id": BOOK_ID,
        "title": "A Tiny Book",
        "author": "Ada Writer",
        "status": "queued",
        "passages_indexed": 0,
        "passages_total": None,
        "error": None,
        "uploaded_at": response_book["uploaded_at"],
        **expected,
    }


def test_upload_queues_the_book(client: TestClient, settings: Settings) -> None:
    """A valid EPUB returns 202 with the book in queued, and stores the file."""
    before = datetime.now(UTC)
    data = make_epub()
    response = upload(client, data)
    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body == book_json(body)
    uploaded_at = datetime.fromisoformat(body["uploaded_at"])
    assert before - timedelta(seconds=1) <= uploaded_at <= datetime.now(UTC)
    stored = Path(settings.file_store_dir) / "books" / f"{BOOK_ID}.epub"
    assert stored.read_bytes() == data


def test_worker_parses_the_book(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """After the worker runs the job, the book is indexing with 0 of N passages."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    response = client.get("/api/books")
    assert response.status_code == HTTPStatus.OK
    [book] = response.json()["books"]
    assert book == book_json(book, status="indexing", passages_total=2)
    assert count(engine, passages) == 2  # noqa: PLR2004
    assert not work(), "the queue is empty"


def test_list_is_empty_without_books(client: TestClient) -> None:
    """GET /api/books returns an empty list before any upload."""
    response = client.get("/api/books")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"books": []}


def test_list_is_newest_first(client: TestClient) -> None:
    """GET /api/books lists the books newest first."""
    for n in range(3):
        book = FixtureBook(identifier=f"isbn-{n}", title=f"Book {n}")
        assert upload(client, make_epub(book)).status_code == HTTPStatus.ACCEPTED
    listed = client.get("/api/books").json()["books"]
    assert [book["title"] for book in listed] == ["Book 2", "Book 1", "Book 0"]
    assert [book["id"] for book in listed] == [
        hashlib.sha256(f"isbn-{n}".encode()).hexdigest()[:16] for n in (2, 1, 0)
    ]


CONTAINER = "META-INF/container.xml"
OPF = "OEBPS/content.opf"
NOT_READABLE = "The file is not a readable EPUB"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"plain text, not a zip file", NOT_READABLE),
        (replace_member(make_epub(), CONTAINER, None), NOT_READABLE),
        (replace_member(make_epub(), CONTAINER, b"<container/>"), NOT_READABLE),
        (replace_member(make_epub(), OPF, None), NOT_READABLE),
        (replace_member(make_epub(), OPF, b"<package"), NOT_READABLE),
        (replace_member(make_epub(), OPF, b"<html/>"), NOT_READABLE),
        (make_epub(FixtureBook(title=None)), "The EPUB has no title"),
        (make_epub(FixtureBook(title="  ")), "The EPUB has no title"),
    ],
    ids=[
        "not-a-zip",
        "no-container",
        "no-rootfile",
        "no-package",
        "broken-package",
        "not-a-package",
        "no-title",
        "blank-title",
    ],
)
def test_unreadable_upload_is_refused(
    client: TestClient, engine: Engine, data: bytes, error: str
) -> None:
    """A file that is not a readable EPUB, or has no title, is 422 with no book."""
    response = upload(client, data)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": error}
    assert count(engine, books) == 0


def test_upload_without_file_is_refused(client: TestClient) -> None:
    """A request without the `file` field is 422."""
    response = client.post("/api/books", data={"other": "x"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": "Send the EPUB in the multipart field 'file'"}


def test_same_book_id_is_refused(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """A book whose ID is in the library is 409 with that ID, and adds nothing."""
    upload(client, make_epub())
    assert work()
    passages_before = count(engine, passages)
    other_file = make_epub(FixtureBook(title="A Tiny Book, Second Edition"))
    response = upload(client, other_file)
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {
        "error": "A book with this ID is already in the library",
        "book_id": BOOK_ID,
    }
    assert count(engine, books) == 1
    assert count(engine, ingestion_jobs) == 1
    assert not work()
    assert count(engine, passages) == passages_before


def test_same_file_is_refused(client: TestClient, engine: Engine) -> None:
    """The same file again is 409 with the existing book's ID."""
    data = make_epub()
    upload(client, data)
    response = upload(client, data, name="copy.epub")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {
        "error": "This file is already in the library",
        "book_id": BOOK_ID,
    }
    assert count(engine, books) == 1


@pytest.mark.parametrize("extra_mb", [1, 2], ids=["read", "content-length"])
def test_upload_over_the_size_limit_is_refused(
    database_url: str, tmp_path: Path, extra_mb: int
) -> None:
    """A file over LIBRAG_MAX_UPLOAD_MB is 413 and creates no book."""
    settings = Settings(
        database_url=database_url,
        file_store_dir=str(tmp_path / "files"),
        max_upload_mb=1,
    )
    too_big = make_epub() + b"\0" * (extra_mb * 1024 * 1024)
    with TestClient(create_app(settings)) as client:
        response = upload(client, too_big)
        assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert response.json() == {"error": "The file is larger than 1 MB"}
        assert client.get("/api/books").json() == {"books": []}


@pytest.mark.parametrize("navigation", ["nav", "ncx", "none"])
def test_book_without_identifier_gets_id_from_title_and_author(
    client: TestClient, navigation: str
) -> None:
    """Without dc:identifier, the ID hashes the normalized title and author."""
    first = FixtureBook(
        identifier=None,
        title="The  Long\tRoad",
        author="Ada WRITER",
        navigation=navigation,  # ty: ignore[invalid-argument-type]
    )
    response = upload(client, make_epub(first))
    assert response.status_code == HTTPStatus.ACCEPTED
    expected = hashlib.sha256(b"the long road\nada writer").hexdigest()[:16]
    assert response.json()["id"] == expected
    same = FixtureBook(
        identifier=None,
        title="the long road",
        author=" Ada  Writer ",
        chapters=TWO_CHAPTERS.chapters,
    )
    again = upload(client, make_epub(same))
    assert again.status_code == HTTPStatus.CONFLICT
    assert again.json()["book_id"] == expected


def test_book_without_author(client: TestClient) -> None:
    """A book without dc:creator has a null author."""
    response = upload(client, make_epub(FixtureBook(author=None)))
    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["author"] is None


def test_book_without_text_fails(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """An EPUB with no extractable text ends in failed with an error."""
    empty = FixtureBook(chapters=(FixtureChapter("<h1>Only a heading</h1><p> </p>"),))
    upload(client, make_epub(empty))
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(book, status="failed", error="No text found in the EPUB")
    assert count(engine, passages) == 0


def test_book_with_a_missing_chapter_fails(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """An EPUB that breaks during parsing ends in failed; the worker goes on."""
    upload(client, replace_member(make_epub(), "OEBPS/text/ch1.xhtml", None))
    upload(client, make_epub(FixtureBook(identifier="isbn-ok")))
    assert work()
    assert work()
    listed = client.get("/api/books").json()["books"]
    assert [(b["status"], b["error"]) for b in listed] == [
        ("indexing", None),
        ("failed", NOT_READABLE),
    ]
    assert count(engine, passages) == 1


def test_book_whose_stored_file_is_gone_fails(
    client: TestClient, settings: Settings, work: Callable[[], bool]
) -> None:
    """An unexpected parse error ends in failed with a general error."""
    upload(client, make_epub())
    (Path(settings.file_store_dir) / "books" / f"{BOOK_ID}.epub").unlink()
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(
        book, status="failed", error="The EPUB could not be parsed"
    )


def test_interrupted_job_runs_again(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """A job left running when the worker stopped runs again when it starts."""
    upload(client, make_epub(TWO_CHAPTERS))
    with engine.begin() as connection:
        connection.execute(update(ingestion_jobs).values(status="running"))
        connection.execute(update(books).values(status="parsing"))
    assert not work(), "a running job is not claimed again"
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "parsing"
    assert requeue_interrupted_jobs(engine) == 1
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(book, status="queued")
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(book, status="indexing", passages_total=2)


def test_book_stores_its_index_configuration(
    database_url: str, tmp_path: Path, engine: Engine
) -> None:
    """The book stores the passage target, overlap and tokenizer it was parsed with."""
    settings = Settings(
        database_url=database_url,
        file_store_dir=str(tmp_path / "files"),
        passage_target_tokens=120,
        passage_overlap_tokens=10,
    )
    with TestClient(create_app(settings)) as client:
        upload(client, make_epub())
    with engine.connect() as connection:
        row = connection.execute(
            select(
                books.c.passage_target_tokens,
                books.c.passage_overlap_tokens,
                books.c.tokenizer,
            )
        ).one()
    assert tuple(row) == (120, 10, "cl100k_base")
