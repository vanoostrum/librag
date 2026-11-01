# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for deleting, retrying and reindexing books, checked through search."""

import dataclasses
import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast, override

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from sqlalchemy import ColumnElement, Engine, Executable, delete, select, update

from librag.books import book_path
from librag.db import books, ingestion_jobs, passages
from librag.embeddings import Embeddings, FakeEmbedder
from librag.epub import read_chapters
from librag.index import Point, ensure_collection, upsert
from librag.main import create_app
from librag.passages import build_passages, passage_id
from librag.settings import Settings
from librag.worker import Indexing, run_one_job
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

SEARCH = "/api/rag/search"
OLD_MODEL = "openai/text-embedding-3-small"


def _id(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


def _book(identifier: str, title: str, *texts: str) -> FixtureBook:
    """Return a fixture book with one chapter, so one passage, per text."""
    return FixtureBook(
        identifier=identifier,
        title=title,
        chapters=tuple(
            FixtureChapter(paragraphs(text), nav_title=f"Part {n}")
            for n, text in enumerate(texts, start=1)
        ),
    )


SEA = _book(
    "urn:sea",
    "Sea Stories",
    "The lighthouse keeper polished the brass lamp every evening.",
    "Wild strawberries grew along the railway embankment.",
)
HARBOUR = _book(
    "urn:harbour",
    "Harbour Tales",
    "A submarine captain charted the coral reef at dawn.",
    "The lighthouse beam swept across the harbour fog.",
)
RIVER = _book(
    "urn:river",
    "River Songs",
    "The ferryman sang to the lighthouse on the far bank.",
)
SEA_ID, HARBOUR_ID, RIVER_ID = _id("urn:sea"), _id("urn:harbour"), _id("urn:river")
# A book with one chapter of 12 paragraphs of about 40 tokens each.
LONG = FixtureBook(
    identifier="urn:long",
    title="Long Letters",
    chapters=(
        FixtureChapter(
            paragraphs(
                *(
                    f"Letter {n} tells of the lighthouse, the harbour and the long "
                    "winter, of ships that came late and of the keeper who waited "
                    "for them on the cold stone pier every night."
                    for n in range(12)
                )
            )
        ),
    ),
)
LONG_ID = _id("urn:long")
PASSAGES = {
    book_id: {passage_id(book_id, position) for position in range(2)}
    for book_id in (SEA_ID, HARBOUR_ID, RIVER_ID)
}


def search_ids(client: TestClient, query: str, **fields: object) -> list[str]:
    """Return the passage IDs of the results and every stage, in order."""
    response = client.post(SEARCH, json={"query": query, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    body = response.json()
    ids: list[str] = [result["passage_id"] for result in body["results"]]
    for stage in body["stages"].values():
        ids += [passage["passage_id"] for passage in stage["passages"]]
    return ids


def book_ids_found(client: TestClient, query: str) -> set[str]:
    """Return the fixture books that have a passage in the results or any stage."""
    found = set(search_ids(client, query))
    return {book_id for book_id, ids in PASSAGES.items() if found & ids}


def listed(client: TestClient) -> dict[str, dict[str, Any]]:
    """Return the books of `GET /api/books`, by ID."""
    return {book["id"]: book for book in client.get("/api/books").json()["books"]}


@dataclass(frozen=True)
class Store:
    """The test database, file store and Qdrant, to check and stage what is inside."""

    engine: Engine
    settings: Settings
    qdrant: QdrantClient
    collection: str

    @property
    def old(self) -> str:
        """The collection of the model that indexed the books before the fake."""
        return f"{self.settings.qdrant_collection_prefix}_openai_text-embedding-3-small"

    def run(self, indexing: Indexing | None = None) -> bool:
        """Run one worker tick, with `indexing` if given."""
        return run_one_job(self.engine, self.settings, indexing)

    def execute(self, statement: Executable) -> None:
        """Run `statement` on the database, for a state no request reaches."""
        with self.engine.begin() as connection:
            connection.execute(statement)

    def set_book(self, book_id: str, **values: object) -> None:
        """Change the book's row, for a state that only the worker or time reaches."""
        self.execute(update(books).where(books.c.id == book_id).values(**values))

    def row(self, book_id: str, *columns: ColumnElement[Any]) -> tuple[Any, ...]:
        """Return the book's values in `columns`."""
        with self.engine.connect() as connection:
            return tuple(
                connection.execute(select(*columns).where(books.c.id == book_id)).one()
            )

    def passages(self, book_id: str) -> list[tuple[str, str]]:
        """Return the IDs and texts of the book's stored passages, in order."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(passages.c.id, passages.c.text)
                .where(passages.c.book_id == book_id)
                .order_by(passages.c.position)
            ).all()
        return [(str(row.id), str(row.text)) for row in rows]

    def jobs(self, book_id: str) -> int:
        """Return how many jobs the book has."""
        with self.engine.connect() as connection:
            return len(
                connection.execute(
                    select(ingestion_jobs).where(ingestion_jobs.c.book_id == book_id)
                ).all()
            )

    def file(self, book_id: str) -> Path:
        """Return where the file store keeps the book's EPUB."""
        return book_path(self.settings.file_store_dir, book_id)

    def points(self, book_id: str, collection: str | None = None) -> int:
        """Return how many points of `book_id` the collection holds."""
        name = collection or self.collection
        if not self.qdrant.collection_exists(name):
            return 0
        return self.qdrant.count(name, count_filter=_of_book(book_id), exact=True).count

    def copy_to_old(self, book_id: str) -> None:
        """Copy the book's points to the old model's collection, as if it made them."""
        records, _ = self.qdrant.scroll(
            self.collection, scroll_filter=_of_book(book_id), with_vectors=True
        )
        points = [
            Point(
                id=str(record.id),
                text=(record.payload or {})["text"],
                vector=cast("list[float]", (record.vector or {})["dense"]),  # ty: ignore[invalid-argument-type]
                payload=record.payload or {},
            )
            for record in records
        ]
        ensure_collection(self.qdrant, self.old, len(points[0].vector))
        upsert(self.qdrant, self.old, points)


def _of_book(book_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(key="book_id", match=models.MatchValue(value=book_id))
        ]
    )


@pytest.fixture
def store(
    engine: Engine, settings: Settings, qdrant: QdrantClient, collection: str
) -> Store:
    """Return the test stores."""
    return Store(engine, settings, qdrant, collection)


@pytest.fixture
def on_settings(settings: Settings) -> Settings:
    """Return the test settings with LIBRAG_REINDEX_ENABLED on."""
    return dataclasses.replace(settings, reindex_enabled=True)


@pytest.fixture
def on(on_settings: Settings, client: TestClient) -> Iterator[TestClient]:
    """Return a test client for the app with the reindex switch on.

    It depends on `client`, so books can be added through either.
    """
    del client
    with TestClient(create_app(on_settings)) as on:
        yield on


class BrokenEmbedder(FakeEmbedder):
    """An embedder whose API is down."""

    @override
    def embed(self, texts: list[str]) -> Embeddings:
        """Fail, as an API outage does."""
        del texts
        msg = "embedding API unavailable"
        raise RuntimeError(msg)


# Delete


def test_delete_removes_the_book_from_every_collection(
    client: TestClient,
    index: Callable[..., None],
    store: Store,
) -> None:
    """DELETE returns 204; the book is gone from the list, search and every collection.

    A second delete returns 404.
    """
    index(SEA, HARBOUR)
    store.copy_to_old(SEA_ID)
    assert store.points(SEA_ID, store.old) == 2  # noqa: PLR2004
    assert SEA_ID in book_ids_found(client, "lighthouse keeper strawberries")

    response = client.delete(f"/api/books/{SEA_ID}")
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""
    assert list(listed(client)) == [HARBOUR_ID]
    assert book_ids_found(client, "lighthouse keeper strawberries") == {HARBOUR_ID}
    assert store.points(SEA_ID) == 0
    assert store.points(SEA_ID, store.old) == 0
    assert store.passages(SEA_ID) == []
    assert store.jobs(SEA_ID) == 0
    assert not store.file(SEA_ID).exists()

    again = client.delete(f"/api/books/{SEA_ID}")
    assert again.status_code == HTTPStatus.NOT_FOUND
    assert again.json() == {"error": "No book with this ID"}


def test_delete_leaves_the_other_books_unchanged(
    client: TestClient, index: Callable[..., None]
) -> None:
    """The other books keep their search results, in the same order and score.

    The stages may reorder: BM25's IDF counts every book in the collection.
    """
    index(SEA, HARBOUR)

    def results() -> list[tuple[str, float]]:
        body = client.post(
            SEARCH,
            json={"query": "lighthouse beam submarine", "book_ids": [HARBOUR_ID]},
        ).json()
        return [(r["passage_id"], r["rerank_score"]) for r in body["results"]]

    before = results()
    assert len(before) == 2  # noqa: PLR2004
    assert client.delete(f"/api/books/{SEA_ID}").status_code == HTTPStatus.NO_CONTENT
    assert results() == before
    assert listed(client)[HARBOUR_ID]["status"] == "indexed"


@pytest.mark.parametrize("status", ["queued", "parsing", "indexing"])
def test_delete_of_a_book_in_progress_is_refused(
    client: TestClient,
    status: str,
    store: Store,
) -> None:
    """While its job is queued or running, a book cannot be deleted: 409."""
    files = {"file": ("book.epub", make_epub(SEA), "application/epub+zip")}
    assert client.post("/api/books", files=files).status_code == HTTPStatus.ACCEPTED
    store.set_book(SEA_ID, status=status)
    response = client.delete(f"/api/books/{SEA_ID}")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {"error": "The book is queued or being indexed"}
    assert list(listed(client)) == [SEA_ID]


def test_delete_of_a_failed_book(
    client: TestClient,
    store: Store,
) -> None:
    """A failed book can be deleted, with its stored EPUB."""
    no_text = FixtureBook(identifier="empty", chapters=(FixtureChapter("<p> </p>"),))
    files = {"file": ("book.epub", make_epub(no_text), "application/epub+zip")}
    book_id = client.post("/api/books", files=files).json()["id"]
    assert store.run()
    assert client.delete(f"/api/books/{book_id}").status_code == HTTPStatus.NO_CONTENT
    assert listed(client) == {}
    assert not store.file(book_id).exists()


def test_delete_of_an_unknown_book_is_404(
    client: TestClient,
) -> None:
    """There is nothing to delete for an ID that no book has."""
    response = client.delete("/api/books/0000000000000000")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"error": "No book with this ID"}


# Retry


def test_retry_indexes_a_failed_book(
    client: TestClient,
    work: Callable[[], bool],
    store: Store,
) -> None:
    """Retry on a failed book returns 202 with it queued; the worker then indexes it."""
    files = {"file": ("book.epub", make_epub(SEA), "application/epub+zip")}
    client.post("/api/books", files=files)
    broken = Indexing(BrokenEmbedder(), retry_delays=())
    assert store.run(broken)
    assert listed(client)[SEA_ID]["status"] == "failed"

    response = client.post(f"/api/books/{SEA_ID}/retry")
    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert (body["id"], body["status"], body["error"]) == (SEA_ID, "queued", None)
    assert (body["passages_indexed"], body["passages_total"]) == (0, None)
    assert work()
    assert listed(client)[SEA_ID]["status"] == "indexed"
    assert SEA_ID in book_ids_found(client, "lighthouse keeper brass lamp")


def test_interrupted_book_shows_as_failed(
    client: TestClient,
    index: Callable[..., None],
    store: Store,
) -> None:
    """A book in indexing whose job is done is interrupted, and shows as failed."""
    index(SEA)
    store.set_book(SEA_ID, status="indexing")
    book = listed(client)[SEA_ID]
    assert (book["status"], book["error"]) == ("failed", "indexing was interrupted")


@pytest.mark.parametrize("status", ["parsing", "indexing"])
def test_retry_indexes_an_interrupted_book(
    client: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    status: str,
    store: Store,
) -> None:
    """Retry works on a book left in progress with a done job, as before LIBRAG-24."""
    index(SEA)
    store.set_book(SEA_ID, status=status)
    response = client.post(f"/api/books/{SEA_ID}/retry")
    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["status"] == "queued"
    assert work()
    assert listed(client)[SEA_ID]["status"] == "indexed"
    assert SEA_ID in book_ids_found(client, "lighthouse keeper brass lamp")


def test_retry_indexes_a_book_with_no_job_left(
    client: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    store: Store,
) -> None:
    """A book in progress whose jobs are gone is interrupted, and Retry indexes it."""
    index(SEA)
    store.execute(delete(ingestion_jobs))
    store.set_book(SEA_ID, status="parsing")
    assert listed(client)[SEA_ID]["status"] == "failed"
    assert client.post(f"/api/books/{SEA_ID}/retry").status_code == HTTPStatus.ACCEPTED
    assert work()
    assert listed(client)[SEA_ID]["status"] == "indexed"


def test_retry_of_an_indexed_or_queued_book_is_refused(
    client: TestClient,
    index: Callable[..., None],
) -> None:
    """Retry on an indexed book, or one whose job is still queued, returns 409."""
    index(SEA)
    files = {"file": ("book.epub", make_epub(HARBOUR), "application/epub+zip")}
    client.post("/api/books", files=files)
    for book_id in (SEA_ID, HARBOUR_ID):
        response = client.post(f"/api/books/{book_id}/retry")
        assert response.status_code == HTTPStatus.CONFLICT
        assert response.json() == {
            "error": "Only a failed or interrupted book can be retried"
        }
    assert [book["status"] for book in listed(client).values()] == [
        "queued",
        "indexed",
    ]


def test_retry_of_an_unknown_book_is_404(
    client: TestClient,
) -> None:
    """There is nothing to retry for an ID that no book has."""
    assert client.post("/api/books/nope/retry").status_code == HTTPStatus.NOT_FOUND


# Reindex


@pytest.mark.parametrize(
    "path", [f"/api/books/{SEA_ID}/reindex", "/api/books/reindex-out-of-date"]
)
def test_reindex_routes_are_404_with_the_switch_off(
    client: TestClient,
    index: Callable[..., None],
    path: str,
) -> None:
    """With LIBRAG_REINDEX_ENABLED off, both reindex routes answer 404."""
    index(SEA)
    response = client.post(path)
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"error": "Reindexing is turned off"}
    assert listed(client)[SEA_ID]["status"] == "indexed"


def test_reindex_rebuilds_the_book_without_duplicates(
    on: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    store: Store,
) -> None:
    """Reindex returns 202; during it search leaves the book out; after it, the same.

    The book has the same passage count again, and no point is duplicated.
    """
    index(SEA, HARBOUR)
    before = store.passages(SEA_ID)
    response = on.post(f"/api/books/{SEA_ID}/reindex")
    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert (body["id"], body["status"], body["passages_total"]) == (
        SEA_ID,
        "queued",
        None,
    )
    assert book_ids_found(on, "lighthouse keeper strawberries") == {HARBOUR_ID}
    assert store.points(SEA_ID) == 0

    assert work()
    book = listed(on)[SEA_ID]
    assert (book["status"], book["passages_total"]) == ("indexed", 2)
    assert store.passages(SEA_ID) == before
    assert store.points(SEA_ID) == 2  # noqa: PLR2004
    results = on.post(SEARCH, json={"query": "lighthouse keeper"}).json()["results"]
    assert len({r["passage_id"] for r in results}) == len(results)
    assert SEA_ID in book_ids_found(on, "lighthouse keeper strawberries")


@pytest.mark.parametrize("status", ["queued", "failed"])
def test_reindex_of_a_book_that_is_not_indexed_is_refused(
    on: TestClient,
    status: str,
    store: Store,
) -> None:
    """Only an indexed book can be reindexed: 409 otherwise."""
    files = {"file": ("book.epub", make_epub(SEA), "application/epub+zip")}
    on.post("/api/books", files=files)
    if status == "failed":
        assert store.run(Indexing(BrokenEmbedder(), ()))
    response = on.post(f"/api/books/{SEA_ID}/reindex")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {"error": "Only an indexed book can be reindexed"}
    assert listed(on)[SEA_ID]["status"] == status


def test_reindex_of_an_unknown_book_is_404(
    on: TestClient,
) -> None:
    """With the switch on, an unknown book is still 404."""
    response = on.post("/api/books/nope/reindex")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"error": "No book with this ID"}


def test_new_embedding_model_reembeds_the_stored_passages(
    on: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    store: Store,
) -> None:
    """After a model change, reindex fills the new model's collection, with no parse.

    The book was indexed with another model; the fake embedder is the model now.
    The stored EPUB is removed, so a new parse would fail the book.
    """
    index(SEA)
    store.copy_to_old(SEA_ID)
    store.qdrant.delete(
        store.collection,
        points_selector=models.FilterSelector(filter=_of_book(SEA_ID)),
        wait=True,
    )
    store.set_book(SEA_ID, embedding_model=OLD_MODEL)
    before = store.passages(SEA_ID)
    store.file(SEA_ID).unlink()

    assert on.post(f"/api/books/{SEA_ID}/reindex").status_code == HTTPStatus.ACCEPTED
    assert work()
    book = listed(on)[SEA_ID]
    assert (book["status"], book["passages_total"]) == ("indexed", 2)
    assert store.passages(SEA_ID) == before
    assert store.row(SEA_ID, books.c.embedding_model) == ("fake",)
    assert store.points(SEA_ID) == 2  # noqa: PLR2004
    assert store.points(SEA_ID, store.old) == 0
    assert SEA_ID in book_ids_found(on, "lighthouse keeper brass lamp")


def test_new_passage_settings_parse_the_book_again(
    client: TestClient,
    index: Callable[..., None],
    on_settings: Settings,
    work: Callable[[], bool],
    store: Store,
) -> None:
    """After a passage settings change, reindex cuts the passages anew."""
    index(LONG)
    old_total = listed(client)[LONG_ID]["passages_total"]
    smaller = dataclasses.replace(
        on_settings, passage_target_tokens=60, passage_overlap_tokens=10
    )
    with TestClient(create_app(smaller)) as changed:
        assert (
            changed.post(f"/api/books/{LONG_ID}/reindex").status_code
            == HTTPStatus.ACCEPTED
        )
        assert work()
        book = listed(changed)[LONG_ID]
    data = store.file(LONG_ID).read_bytes()
    expected = build_passages(read_chapters(data), 60, 10)
    assert book["status"] == "indexed"
    assert book["passages_total"] == len(expected) != old_total
    assert [text for _, text in store.passages(LONG_ID)] == [
        passage.text for passage in expected
    ]
    assert store.points(LONG_ID) == len(expected)
    columns = (books.c.passage_target_tokens, books.c.passage_overlap_tokens)
    assert store.row(LONG_ID, *columns) == (60, 10)


def test_reindex_out_of_date_reindexes_only_out_of_date_books(
    on: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    store: Store,
) -> None:
    """Reindex out-of-date queues the out-of-date books, and no other."""
    index(SEA, HARBOUR, RIVER)
    store.set_book(SEA_ID, embedding_model=OLD_MODEL)
    store.set_book(HARBOUR_ID, passage_target_tokens=500)
    response = on.post("/api/books/reindex-out-of-date")
    assert response.status_code == HTTPStatus.ACCEPTED
    assert sorted(response.json()["book_ids"]) == sorted([SEA_ID, HARBOUR_ID])
    statuses = {book_id: book["status"] for book_id, book in listed(on).items()}
    assert statuses == {SEA_ID: "queued", HARBOUR_ID: "queued", RIVER_ID: "indexed"}
    assert book_ids_found(on, "lighthouse") == {RIVER_ID}
    assert work()
    assert work()
    assert not work()
    assert {book["status"] for book in listed(on).values()} == {"indexed"}
    assert store.row(SEA_ID, books.c.embedding_model) == ("fake",)

    again = on.post("/api/books/reindex-out-of-date")
    assert again.status_code == HTTPStatus.ACCEPTED
    assert again.json() == {"book_ids": []}


def test_reindex_of_a_book_without_stored_passages_parses_it(
    on: TestClient,
    index: Callable[..., None],
    work: Callable[[], bool],
    store: Store,
) -> None:
    """A re-embed with no stored passages to reuse parses the EPUB after all."""
    index(SEA)
    store.set_book(SEA_ID, embedding_model=OLD_MODEL)
    store.execute(delete(passages))
    assert on.post(f"/api/books/{SEA_ID}/reindex").status_code == HTTPStatus.ACCEPTED
    assert work()
    assert listed(on)[SEA_ID]["passages_total"] == 2  # noqa: PLR2004
    assert len(store.passages(SEA_ID)) == 2  # noqa: PLR2004
