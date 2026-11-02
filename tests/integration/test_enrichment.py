# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for contextual enrichment: indexing, search, chat, books and reindex."""

import dataclasses
import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, override

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import Engine, select, update

from librag.books import book_path
from librag.db import books, passages
from librag.embeddings import FakeEmbedder
from librag.enrichment import Enrichment, FakeEnricher
from librag.main import create_app
from librag.passages import Passage, passage_id
from librag.settings import Settings
from librag.worker import Indexing, run_one_job
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
from tests.integration.test_chat_stream import events, named

SEARCH = "/api/rag/search"
KEEPER_TEXT = "The lighthouse keeper polished the brass lamp every evening."
BERRY_TEXT = "Wild strawberries grew along the railway embankment."
SEA = FixtureBook(
    identifier="urn:sea",
    title="Sea Stories",
    chapters=(
        FixtureChapter(paragraphs(KEEPER_TEXT), nav_title="Part 1"),
        FixtureChapter(paragraphs(BERRY_TEXT), nav_title="Part 2"),
    ),
)
SEA_ID = hashlib.sha256(b"urn:sea").hexdigest()[:16]
KEEPER, BERRY = passage_id(SEA_ID, 0), passage_id(SEA_ID, 1)
FAKE_LINES = {
    KEEPER: "About Part 1: The lighthouse keeper polished the",
    BERRY: "About Part 2: Wild strawberries grew along the",
}
OLD_MODEL = "openai/text-embedding-3-small"


@pytest.fixture
def enrich_settings(settings: Settings) -> Settings:
    """Return the test settings with enrichment and the reindex switch on."""
    return dataclasses.replace(settings, enrichment=True, reindex_enabled=True)


@pytest.fixture
def enriched(enrich_settings: Settings, client: TestClient) -> Iterator[TestClient]:
    """Return a client with enrichment on, which shares the stores of `client`."""
    del client
    with TestClient(create_app(enrich_settings)) as enriched:
        yield enriched


@pytest.fixture
def work_on(engine: Engine, enrich_settings: Settings) -> Callable[[], bool]:
    """Return a function that runs one worker tick with enrichment on."""
    return lambda: run_one_job(engine, enrich_settings)


@pytest.fixture
def plain(settings: Settings, client: TestClient) -> Iterator[TestClient]:
    """Return a client with enrichment off and the reindex switch on."""
    del client
    on = dataclasses.replace(settings, reindex_enabled=True)
    with TestClient(create_app(on)) as plain:
        yield plain


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the passage of every call to the fake enricher."""
    made: list[str] = []
    enrich = FakeEnricher.enrich

    def counted(self: FakeEnricher, chapter: str, passage: Passage) -> Enrichment:
        made.append(passage.text)
        return enrich(self, chapter, passage)

    monkeypatch.setattr(FakeEnricher, "enrich", counted)
    return made


def upload(client: TestClient, book: FixtureBook = SEA) -> None:
    """Upload the fixture book."""
    files = {"file": ("book.epub", make_epub(book), "application/epub+zip")}
    response = client.post("/api/books", files=files)
    assert response.status_code == HTTPStatus.ACCEPTED, response.text


def search(client: TestClient, query: str, **fields: object) -> dict[str, Any]:
    """Return the search response body for `query`."""
    response = client.post(SEARCH, json={"query": query, **fields})
    assert response.status_code == HTTPStatus.OK, response.text
    return response.json()


def listed(client: TestClient) -> dict[str, Any]:
    """Return the fixture book as `GET /api/books` shows it."""
    return {b["id"]: b for b in client.get("/api/books").json()["books"]}[SEA_ID]


@dataclass(frozen=True)
class Stores:
    """The test database and Qdrant collection, to check what indexing wrote."""

    engine: Engine
    qdrant: QdrantClient
    collection: str
    file_store_dir: str

    def passages(self) -> list[tuple[str, str, str | None]]:
        """Return the ID, text and context line of each stored passage, in order."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(passages.c.id, passages.c.text, passages.c.context).order_by(
                    passages.c.position
                )
            ).all()
        return [(row.id, row.text, row.context) for row in rows]

    def contexts(self) -> list[str | None]:
        """Return the context line of each stored passage, in order."""
        return [context for _, _, context in self.passages()]

    def payloads(self) -> dict[str, dict[str, Any]]:
        """Return the Qdrant payload of each point in the collection, by ID."""
        records, _ = self.qdrant.scroll(self.collection, limit=100)
        return {str(record.id): record.payload or {} for record in records}


@pytest.fixture
def stores(
    engine: Engine, qdrant: QdrantClient, collection: str, settings: Settings
) -> Stores:
    """Return the test stores."""
    return Stores(engine, qdrant, collection, settings.file_store_dir)


def out_of_date_note(client: TestClient) -> str | None:
    """Return the out-of-date note on the book's Library card, if it has one."""
    html = client.get("/library/books").text
    marker = "Out of date: "
    start = html.find(marker)
    return None if start < 0 else html[start : html.index("<", start)].strip()


# Off


def test_enrichment_off_indexes_as_before(
    client: TestClient,
    work: Callable[[], bool],
    stores: Stores,
    calls: list[str],
) -> None:
    """With the switch off: no enrichment calls, no context lines, no model."""
    upload(client)
    assert work()
    assert calls == []
    assert stores.contexts() == [None, None]
    assert all("context" not in payload for payload in stores.payloads())
    book = listed(client)
    assert book["index_configuration"]["enrichment_model"] is None
    assert (
        book["enrichment_input_tokens"],
        book["enrichment_output_tokens"],
        book["enrichment_cost_usd"],
    ) == (0, 0, 0.0)
    body = search(client, "lighthouse keeper")
    assert body["results"][0]["passage_id"] == KEEPER
    assert body["results"][0]["text"] == KEEPER_TEXT
    assert {r["context"] for r in body["results"]} == {None}
    assert {c["context"] for c in body["candidates"]} == {None}


# On


def test_enrichment_on_gives_every_passage_a_context_line(
    enriched: TestClient,
    work_on: Callable[[], bool],
    stores: Stores,
) -> None:
    """Each passage gets a line; search returns it apart from the original text."""
    upload(enriched)
    assert work_on()
    assert stores.passages() == [
        (KEEPER, KEEPER_TEXT, FAKE_LINES[KEEPER]),
        (BERRY, BERRY_TEXT, FAKE_LINES[BERRY]),
    ]
    found = stores.payloads()
    assert {pid: found[pid]["context"] for pid in found} == FAKE_LINES
    assert {pid: found[pid]["text"] for pid in found} == {
        KEEPER: KEEPER_TEXT,
        BERRY: BERRY_TEXT,
    }

    body = search(enriched, "lighthouse strawberries")
    texts = {KEEPER: KEEPER_TEXT, BERRY: BERRY_TEXT}
    assert {r["passage_id"] for r in body["results"]} == {KEEPER, BERRY}
    for item in [*body["results"], *body["candidates"]]:
        assert item["context"] == FAKE_LINES[item["passage_id"]]
        assert item["text"] == texts[item["passage_id"]]


def test_books_list_reports_the_enrichment_model_tokens_and_cost(
    enriched: TestClient, work_on: Callable[[], bool]
) -> None:
    """The fake counts words as tokens: chapter and passage in, the line out."""
    upload(enriched)
    assert work_on()
    book = listed(enriched)
    assert book["index_configuration"]["enrichment_model"] == "fake"
    # Per passage: its chapter, which is the passage itself, and the passage.
    assert book["enrichment_input_tokens"] == 2 * (9 + 7)
    assert book["enrichment_output_tokens"] == 8 + 8
    assert book["enrichment_cost_usd"] == 0.0


class Keeper(FakeEnricher):
    """An enricher whose line names what the passage text does not."""

    @override
    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Name the lighthouse of the keeper; others get the fake line."""
        if "keeper" in passage.text:
            return Enrichment("Eddystone, where Abel Nightingale works", 3, 5, 0.01)
        return super().enrich(chapter, passage)


def test_bm25_finds_a_passage_by_words_only_in_its_context_line(
    client: TestClient, engine: Engine, settings: Settings
) -> None:
    """A query on the context line's words finds the passage through BM25."""
    upload(client)
    indexing = Indexing(FakeEmbedder(), enricher=Keeper())
    assert run_one_job(engine, settings, indexing)
    body = search(client, "Eddystone Nightingale")
    bm25 = [p["passage_id"] for p in body["stages"]["bm25"]["passages"]]
    assert bm25 == [KEEPER]
    assert body["results"][0]["passage_id"] == KEEPER
    assert body["results"][0]["text"] == KEEPER_TEXT
    assert "Eddystone" not in KEEPER_TEXT
    # Its cost is added up with the fake line's, which costs 0.
    assert listed(client)["enrichment_cost_usd"] == pytest.approx(0.01)


def test_bm25_does_not_find_context_words_without_enrichment(
    client: TestClient, work: Callable[[], bool]
) -> None:
    """Without enrichment, the same query finds nothing through BM25."""
    upload(client)
    assert work()
    body = search(client, "Eddystone Nightingale")
    assert body["stages"]["bm25"]["passages"] == []


def test_chat_cites_the_original_text_only(
    enriched: TestClient, work_on: Callable[[], bool]
) -> None:
    """Citations, their sources and the diagnostics hold no context line."""
    upload(enriched)
    assert work_on()
    question = {"question": "Who polished the lamp?", "book_ids": [SEA_ID]}
    response = enriched.post("/api/chat", json=question)
    assert response.status_code == HTTPStatus.OK, response.text
    body = response.json()
    assert body["citations"]
    texts = {KEEPER: KEEPER_TEXT, BERRY: BERRY_TEXT}
    for citation in body["citations"]:
        assert "context" not in citation
        assert citation["text"] == texts[citation["passage_id"]]
    assert "About Part" not in response.text

    streamed = enriched.post("/api/chat/stream", json=question)
    assert streamed.status_code == HTTPStatus.OK
    assert "About Part" not in streamed.text
    sources = [
        source
        for part in named(events(streamed.text), "part")
        for source in part["sources"]
    ]
    assert sources
    assert {source["text"] for source in sources} <= set(texts.values())
    assert all("context" not in source for source in sources)
    done = named(events(streamed.text), "done")
    assert "About Part" not in json.dumps(done)


# Out of date and reindex


def test_book_without_enrichment_is_out_of_date_when_it_is_turned_on(
    plain: TestClient,
    enriched: TestClient,
    work: Callable[[], bool],
    work_on: Callable[[], bool],
) -> None:
    """Turning enrichment on marks the book out of date, until it is reindexed."""
    upload(plain)
    assert work()
    assert out_of_date_note(plain) is None
    assert out_of_date_note(enriched) == "Out of date: indexed without enrichment"
    response = enriched.post("/api/books/reindex-out-of-date")
    assert response.json() == {"book_ids": [SEA_ID]}
    assert work_on()
    assert out_of_date_note(enriched) is None


def test_book_with_enrichment_is_out_of_date_when_it_is_turned_off(
    plain: TestClient, enriched: TestClient, work_on: Callable[[], bool]
) -> None:
    """A book indexed with enrichment is out of date once it is off."""
    upload(enriched)
    assert work_on()
    assert out_of_date_note(enriched) is None
    assert out_of_date_note(plain) == "Out of date: indexed with enrichment"


def test_book_enriched_with_another_model_is_out_of_date(
    enriched: TestClient, work_on: Callable[[], bool], stores: Stores
) -> None:
    """The reason names the model that wrote the lines."""
    upload(enriched)
    assert work_on()
    with stores.engine.begin() as connection:
        connection.execute(
            update(books).values(enrichment_model="anthropic/claude-haiku-4-5")
        )
    assert out_of_date_note(enriched) == "Out of date: enriched with claude-haiku-4-5"


def test_reindex_enriches_the_stored_passages_without_a_parse(
    plain: TestClient,
    enriched: TestClient,
    work: Callable[[], bool],
    work_on: Callable[[], bool],
    stores: Stores,
) -> None:
    """Reindex writes the lines and re-embeds; the passages and their IDs stay.

    The stored EPUB is removed, so a new parse would fail the book.
    """
    upload(plain)
    assert work()
    before = [(pid, text) for pid, text, _ in stores.passages()]
    book_path(stores.file_store_dir, SEA_ID).unlink()

    reindexed = enriched.post(f"/api/books/{SEA_ID}/reindex")
    assert reindexed.status_code == HTTPStatus.ACCEPTED
    assert work_on()
    book = listed(enriched)
    assert (book["status"], book["error"]) == ("indexed", None)
    assert book["index_configuration"]["enrichment_model"] == "fake"
    assert stores.passages() == [(pid, text, FAKE_LINES[pid]) for pid, text in before]
    found = stores.payloads()
    assert {pid: found[pid].get("context") for pid in found} == FAKE_LINES
    assert out_of_date_note(enriched) is None

    # Turning it off again takes the lines out, still without a parse.
    assert plain.post(f"/api/books/{SEA_ID}/reindex").status_code == (
        HTTPStatus.ACCEPTED
    )
    assert work()
    assert listed(plain)["status"] == "indexed"
    assert stores.passages() == [(pid, text, None) for pid, text in before]
    assert all("context" not in p for p in stores.payloads().values())
    assert listed(plain)["enrichment_input_tokens"] == 0


def test_new_embedding_model_reuses_the_stored_context_lines(
    enriched: TestClient,
    work_on: Callable[[], bool],
    stores: Stores,
    calls: list[str],
) -> None:
    """After a model change, reindex re-embeds with the lines it has: no LLM call."""
    upload(enriched)
    assert work_on()
    assert len(calls) == 2  # noqa: PLR2004
    spent = listed(enriched)
    with stores.engine.begin() as connection:
        connection.execute(update(books).values(embedding_model=OLD_MODEL))
    assert out_of_date_note(enriched) == (
        "Out of date: indexed with text-embedding-3-small"
    )

    assert enriched.post(f"/api/books/{SEA_ID}/reindex").status_code == (
        HTTPStatus.ACCEPTED
    )
    assert work_on()
    assert len(calls) == 2  # noqa: PLR2004
    book = listed(enriched)
    assert book["status"] == "indexed"
    assert stores.contexts() == list(FAKE_LINES.values())
    found = stores.payloads()
    assert {pid: found[pid]["context"] for pid in found} == FAKE_LINES
    # The lines in use keep what writing them cost.
    tokens = ("enrichment_input_tokens", "enrichment_output_tokens")
    assert [book[key] for key in tokens] == [spent[key] for key in tokens]


class BrokenEnricher(FakeEnricher):
    """An enricher whose provider is down."""

    @override
    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Fail, as an API outage does."""
        msg = "enrichment API unavailable"
        raise RuntimeError(msg)


def test_failing_enrichment_fails_the_job_and_retry_runs_it_again(
    enriched: TestClient,
    work_on: Callable[[], bool],
    enrich_settings: Settings,
    stores: Stores,
) -> None:
    """After the retries, the book fails with the error; Retry indexes it."""
    upload(enriched)
    waits: list[float] = []
    broken = Indexing(FakeEmbedder(), sleep=waits.append, enricher=BrokenEnricher())
    assert run_one_job(stores.engine, enrich_settings, broken)
    assert waits == [1.0, 2.0, 4.0]
    book = listed(enriched)
    assert (book["status"], book["error"]) == (
        "failed",
        "Enrichment failed: enrichment API unavailable",
    )

    retried = enriched.post(f"/api/books/{SEA_ID}/retry")
    assert retried.status_code == HTTPStatus.ACCEPTED
    assert work_on()
    book = listed(enriched)
    assert (book["status"], book["error"]) == ("indexed", None)
    assert stores.contexts() == list(FAKE_LINES.values())


class Blank(FakeEnricher):
    """An enricher whose model replies with nothing, and counts its calls."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.calls = 0

    @override
    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Return an empty line."""
        self.calls += 1
        return Enrichment("", 4, 0, 0.01)


def test_blank_context_lines_are_reused_after_an_embedding_model_change(
    plain: TestClient, stores: Stores, settings: Settings
) -> None:
    """An empty line counts as written: a model change makes no LLM calls."""
    upload(plain)
    blank = Blank()
    indexing = Indexing(FakeEmbedder(), enricher=blank)
    assert run_one_job(stores.engine, settings, indexing)
    assert (blank.calls, stores.contexts()) == (2, ["", ""])
    with stores.engine.begin() as connection:
        connection.execute(update(books).values(embedding_model=OLD_MODEL))

    reindexed = plain.post(f"/api/books/{SEA_ID}/reindex")
    assert reindexed.status_code == HTTPStatus.ACCEPTED
    assert run_one_job(stores.engine, settings, indexing)
    assert (blank.calls, stores.contexts()) == (2, ["", ""])
    book = listed(plain)
    assert book["status"] == "indexed"
    assert book["enrichment_cost_usd"] == pytest.approx(0.02)
