# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for uploading books with POST /api/books and listing them with GET."""

import hashlib
import io
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, override

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from qdrant_client import QdrantClient, models
from sqlalchemy import Engine, func, insert, select, update

from librag.db import books, ingestion_jobs, passages
from librag.embeddings import Embeddings, FakeEmbedder
from librag.main import create_app
from librag.passages import passage_id
from librag.settings import Settings
from librag.worker import Indexing, requeue_interrupted_jobs, run_one_job
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
        "embedding_tokens": 0,
        "embedding_cost_usd": 0.0,
        "uploaded_at": response_book["uploaded_at"],
        "index_configuration": {
            "passage_target_tokens": 350,
            "passage_overlap_tokens": 50,
            "tokenizer": "cl100k_base",
            "embedding_model": None,
        },
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


def test_worker_indexes_the_book(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """After the worker runs the job, the book is indexed with all its passages."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    response = client.get("/api/books")
    assert response.status_code == HTTPStatus.OK
    [book] = response.json()["books"]
    assert book["embedding_tokens"] > 0
    assert book == book_json(
        book,
        status="indexed",
        passages_indexed=2,
        passages_total=2,
        embedding_tokens=book["embedding_tokens"],
        embedding_cost_usd=0.0,
        index_configuration={
            "passage_target_tokens": 350,
            "passage_overlap_tokens": 50,
            "tokenizer": "cl100k_base",
            "embedding_model": "fake",
        },
    )
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
TOO_LARGE_INSIDE = "The EPUB holds a file larger than 32 MB once unpacked"
SPINE_TOO_LARGE = "The EPUB's text is larger than 256 MB once unpacked"


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
        ("indexed", None),
        ("failed", NOT_READABLE),
    ]
    assert count(engine, passages) == 1


def _zip_bomb(member: str) -> bytes:
    """Return the fixture EPUB with `member` unpacking to just over 32 MB."""
    big = b"<html><body><p>" + b"a" * (32 * 1024 * 1024) + b"</p></body></html>"
    return replace_member(make_epub(), member, big, deflate=True)


def test_upload_that_unpacks_too_large_is_refused(
    client: TestClient, engine: Engine
) -> None:
    """A small EPUB whose package file unpacks to over 32 MB is 422."""
    data = _zip_bomb(OPF)
    assert len(data) < 1024 * 1024
    response = upload(client, data)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": TOO_LARGE_INSIDE}
    assert count(engine, books) == 0


def test_chapter_that_unpacks_too_large_fails(
    client: TestClient, work: Callable[[], bool]
) -> None:
    """A chapter that unpacks to over 32 MB ends the book in failed."""
    upload(client, _zip_bomb("OEBPS/text/ch1.xhtml"))
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(book, status="failed", error=TOO_LARGE_INSIDE)


def test_spine_that_unpacks_too_large_fails(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """A spine that lists one large chapter many times ends the book in failed."""
    chapter = b"<html><body><p>" + b"a" * (1024 * 1024) + b"</p></body></html>"
    epub = replace_member(make_epub(), "OEBPS/text/ch1.xhtml", chapter, deflate=True)
    with zipfile.ZipFile(io.BytesIO(epub)) as archive:
        opf = archive.read(OPF)
    repeated = opf.replace(b'<itemref idref="ch1"/>', b'<itemref idref="ch1"/>' * 257)
    data = replace_member(epub, OPF, repeated)
    assert len(data) < 64 * 1024
    upload(client, data)
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book == book_json(book, status="failed", error=SPINE_TOO_LARGE)
    assert count(engine, passages) == 0


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
    assert book["status"] == "indexed"


def test_job_interrupted_while_indexing_runs_again(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """A job left running while its book was indexing is queued again."""
    upload(client, make_epub(TWO_CHAPTERS))
    with engine.begin() as connection:
        connection.execute(update(ingestion_jobs).values(status="running"))
        connection.execute(update(books).values(status="indexing"))
    assert requeue_interrupted_jobs(engine) == 1
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "queued"
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "indexed"


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


def test_book_records_its_embedding_configuration(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """The book's index configuration adds the embedding model, size and BM25."""
    upload(client, make_epub())
    assert work()
    with engine.connect() as connection:
        row = connection.execute(
            select(
                books.c.embedding_model,
                books.c.embedding_vector_size,
                books.c.bm25_method,
            )
        ).one()
    assert tuple(row) == ("fake", 256, "qdrant/bm25")


def test_collection_has_a_dense_and_a_bm25_vector(
    client: TestClient,
    work: Callable[[], bool],
    qdrant: QdrantClient,
    collection: str,
) -> None:
    """The model's collection has `dense` (cosine, 256) and `bm25` (IDF) vectors."""
    upload(client, make_epub())
    assert work()
    params = qdrant.get_collection(collection).config.params
    assert params.vectors == {
        "dense": models.VectorParams(size=256, distance=models.Distance.COSINE)
    }
    assert params.sparse_vectors == {
        "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
    }
    schema = qdrant.get_collection(collection).payload_schema
    assert {field: info.data_type for field, info in schema.items()} == {
        "book_id": models.PayloadSchemaType.KEYWORD,
        "author": models.PayloadSchemaType.KEYWORD,
    }


def _points(qdrant: QdrantClient, collection: str) -> list[models.Record]:
    points, _ = qdrant.scroll(collection, limit=1000, with_vectors=True)
    return sorted(points, key=lambda point: int((point.payload or {})["position"]))


def test_collection_holds_one_point_per_passage(
    client: TestClient,
    work: Callable[[], bool],
    qdrant: QdrantClient,
    collection: str,
) -> None:
    """Each passage is a point under its passage ID, with its text and location."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    points = _points(qdrant, collection)
    assert [str(point.id) for point in points] == [
        passage_id(BOOK_ID, 0),
        passage_id(BOOK_ID, 1),
    ]
    assert points[1].payload == {
        "book_id": BOOK_ID,
        "title": "A Tiny Book",
        "author": "Ada Writer",
        "text": "Second chapter text.",
        "position": 1,
        "chapter_title": "Two",
        "section_title": None,
        "spine_index": 1,
        "first_paragraph": 0,
        "last_paragraph": 0,
    }
    vectors = points[1].vector
    assert isinstance(vectors, dict)
    dense = vectors["dense"]
    assert isinstance(dense, list)
    assert len(dense) == 256  # noqa: PLR2004
    assert isinstance(vectors["bm25"], models.SparseVector)
    assert vectors["bm25"].indices


def test_bm25_matches_the_book_title_chapter_and_text(
    client: TestClient,
    work: Callable[[], bool],
    qdrant: QdrantClient,
    collection: str,
) -> None:
    """The BM25 vector indexes the title, chapter heading and passage text."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    for query, positions in [("second", [1]), ("tiny", [0, 1]), ("two", [1])]:
        found = qdrant.query_points(
            collection,
            query=models.Document(text=query, model="qdrant/bm25"),
            using="bm25",
        ).points
        assert sorted((p.payload or {})["position"] for p in found) == positions


def test_running_the_job_again_keeps_the_point_count(
    client: TestClient,
    engine: Engine,
    work: Callable[[], bool],
    qdrant: QdrantClient,
    collection: str,
) -> None:
    """A second run of the book's job overwrites its points and adds none."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    before = qdrant.count(collection).count
    with engine.begin() as connection:
        connection.execute(
            insert(ingestion_jobs).values(
                book_id=BOOK_ID, status="queued", created_at=datetime.now(UTC)
            )
        )
    assert work()
    assert qdrant.count(collection).count == before == 2  # noqa: PLR2004
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "indexed"


class FlakyEmbedder(FakeEmbedder):
    """The fake embedder, but the calls listed in `fail_on` raise."""

    def __init__(self, fail_on: set[int], cost_usd: float | None = 0.0) -> None:
        """Fail on the call numbers in `fail_on`, counted from 1."""
        self.fail_on = fail_on
        self.cost_usd = cost_usd
        self.batches: list[int] = []

    @override
    def embed(self, texts: list[str]) -> Embeddings:
        """Record the batch size, then fail or embed."""
        self.batches.append(len(texts))
        if len(self.batches) in self.fail_on:
            msg = "the embedding API is down"
            raise ConnectionError(msg)
        embeddings = super().embed(texts)
        return Embeddings(embeddings.vectors, embeddings.tokens, self.cost_usd)


def chapters(n: int) -> FixtureBook:
    """Return a book with `n` one-paragraph chapters, so `n` passages."""
    return FixtureBook(
        chapters=tuple(
            FixtureChapter(paragraphs(f"Chapter {i} text."), nav_title=f"C{i}")
            for i in range(n)
        )
    )


def test_embedder_that_keeps_failing_fails_the_book(
    client: TestClient, engine: Engine, settings: Settings
) -> None:
    """After 3 retries, after 1, 2 and 4 seconds, the book ends in failed."""
    upload(client, make_epub(chapters(70)))
    embedder = FlakyEmbedder(fail_on={2, 3, 4, 5})
    waits: list[float] = []
    assert run_one_job(engine, settings, Indexing(embedder, sleep=waits.append))
    assert embedder.batches == [64, 6, 6, 6, 6]
    assert waits == [1.0, 2.0, 4.0]
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "failed"
    assert book["error"] == "Indexing failed: the embedding API is down"
    assert (book["passages_indexed"], book["passages_total"]) == (64, 70)
    with engine.connect() as connection:
        job_status = connection.scalar(select(ingestion_jobs.c.status))
    assert job_status == "failed"


def test_embedder_that_recovers_indexes_the_book(
    client: TestClient, engine: Engine, settings: Settings
) -> None:
    """A batch that fails once is retried, and the book ends in indexed."""
    upload(client, make_epub(chapters(70)))
    embedder = FlakyEmbedder(fail_on={1}, cost_usd=None)
    waits: list[float] = []
    assert run_one_job(engine, settings, Indexing(embedder, sleep=waits.append))
    assert embedder.batches == [64, 64, 6]
    assert waits == [1.0]
    [book] = client.get("/api/books").json()["books"]
    assert (book["status"], book["passages_indexed"]) == ("indexed", 70)
    assert book["embedding_cost_usd"] is None, "LiteLLM did not know the price"


def test_fake_providers_call_no_external_api(
    client: TestClient, work: Callable[[], bool], no_internet: list[object]
) -> None:
    """With LIBRAG_AI_PROVIDERS=fake, indexing connects only to this machine."""
    upload(client, make_epub(TWO_CHAPTERS))
    assert work()
    [book] = client.get("/api/books").json()["books"]
    assert book["status"] == "indexed"
    assert no_internet == []
