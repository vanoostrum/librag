# Copyright (C) 2026 Theo van Oostrum
"""The worker process: it writes heartbeats and runs ingestion jobs, one at a time."""

import logging
import signal
import socket
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import FrameType

from sqlalchemy import Engine, create_engine, delete, insert, select, update

from librag.books import book_path
from librag.db import books, ingestion_jobs, passages, to_db_time, worker_heartbeats
from librag.embeddings import Embedder, Embeddings, make_embedder
from librag.epub import EpubError, read_chapters
from librag.index import (
    BM25_METHOD,
    Point,
    collection_name,
    ensure_collection,
    qdrant_client,
    upsert,
)
from librag.passages import Passage, build_passages, passage_id
from librag.settings import Settings

# The worker looks for a queued job, and writes a heartbeat, this often.
POLL_INTERVAL_SECONDS = 1.0
NO_TEXT = "No text found in the EPUB"
UNEXPECTED_FAILURE = "The EPUB could not be parsed"
EMBEDDING_BATCH_SIZE = 64
# A failed batch is tried again after each of these waits, then the book fails.
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)

Clock = Callable[[], datetime]
Sleep = Callable[[float], None]


@dataclass(frozen=True)
class Indexing:
    """How a job indexes: its embedder, and the waits before it retries a batch."""

    embedder: Embedder
    retry_delays: Sequence[float] = RETRY_DELAYS_SECONDS
    sleep: Sleep = time.sleep

    def with_retries[T](self, action: Callable[[], T]) -> T:
        """Return what `action` returns, trying again after each delay if it raises."""
        for delay in self.retry_delays:
            try:
                return action()
            except Exception:
                logger.warning(
                    "indexing batch failed, retrying in %s s", delay, exc_info=True
                )
                self.sleep(delay)
        return action()


logger = logging.getLogger("librag.worker")


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


def tick(engine: Engine, worker_id: str, clock: Clock = utc_now) -> None:
    """Write one heartbeat for `worker_id`, at the time `clock` gives."""
    beat_at = to_db_time(clock())
    with engine.begin() as connection:
        updated = connection.execute(
            update(worker_heartbeats)
            .where(worker_heartbeats.c.worker_id == worker_id)
            .values(beat_at=beat_at)
        )
        if updated.rowcount == 0:
            connection.execute(
                insert(worker_heartbeats).values(worker_id=worker_id, beat_at=beat_at)
            )


def requeue_interrupted_jobs(engine: Engine) -> int:
    """Put jobs that were running when the worker stopped back in the queue.

    Parsing is deterministic, and points are written under the passage IDs, so
    running a job again gives the same passages and points. Returns the number
    of jobs put back.
    """
    with engine.begin() as connection:
        book_ids = connection.scalars(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.status == "running")
            .values(status="queued", started_at=None)
            .returning(ingestion_jobs.c.book_id)
        ).all()
        connection.execute(
            update(books)
            .where(
                books.c.id.in_(book_ids), books.c.status.in_(("parsing", "indexing"))
            )
            .values(status="queued")
        )
    return len(book_ids)


def _claim(engine: Engine) -> tuple[int, str] | None:
    """Mark the oldest queued job as running, and return its ID and book ID."""
    oldest = (
        select(ingestion_jobs.c.id)
        .where(ingestion_jobs.c.status == "queued")
        .order_by(ingestion_jobs.c.id)
        .limit(1)
        .scalar_subquery()
    )
    with engine.begin() as connection:
        claimed = connection.execute(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.id == oldest, ingestion_jobs.c.status == "queued")
            .values(status="running", started_at=to_db_time(utc_now()))
            .returning(ingestion_jobs.c.id, ingestion_jobs.c.book_id)
        ).first()
        if claimed is None:
            return None
        connection.execute(
            update(books).where(books.c.id == claimed.book_id).values(status="parsing")
        )
    return int(claimed.id), str(claimed.book_id)


def _finish(engine: Engine, job_id: int, book: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.id == job_id)
            .values(
                status="failed" if book["status"] == "failed" else "done",
                finished_at=to_db_time(utc_now()),
            )
        )
        connection.execute(
            update(books).where(books.c.id == book.pop("id")).values(**book)
        )


def _index(
    engine: Engine,
    settings: Settings,
    indexing: Indexing,
    book_id: str,
    built: list[Passage],
) -> str | None:
    """Embed and upsert the passages in batches. Return the error, if any.

    The book's progress, embedding tokens and cost move on after each batch.
    """
    with engine.connect() as connection:
        title, author = connection.execute(
            select(books.c.title, books.c.author).where(books.c.id == book_id)
        ).one()
    embedder = indexing.embedder
    name = collection_name(settings.qdrant_collection_prefix, embedder.model)
    client = qdrant_client(settings.qdrant_url)
    tokens, cost = 0, 0.0

    def index_batch(batch: list[Passage]) -> Embeddings:
        # The indexed text is the book title, chapter heading and passage text.
        texts = [
            f"{title}\n{passage.chapter_title}\n{passage.text}" for passage in batch
        ]
        embeddings = embedder.embed(texts)
        ensure_collection(client, name, len(embeddings.vectors[0]))
        upsert(
            client,
            name,
            [
                Point(
                    id=passage_id(book_id, passage.position),
                    text=text,
                    vector=vector,
                    payload={
                        "book_id": book_id,
                        "title": title,
                        "author": author,
                        "text": passage.text,
                        "position": passage.position,
                        "chapter_title": passage.chapter_title,
                        "section_title": passage.section_title,
                        "spine_index": passage.spine_index,
                        "first_paragraph": passage.first_paragraph,
                        "last_paragraph": passage.last_paragraph,
                    },
                )
                for passage, text, vector in zip(
                    batch, texts, embeddings.vectors, strict=True
                )
            ],
        )
        return embeddings

    try:
        for start in range(0, len(built), EMBEDDING_BATCH_SIZE):
            batch = built[start : start + EMBEDDING_BATCH_SIZE]
            try:
                embeddings = indexing.with_retries(
                    lambda batch=batch: index_batch(batch)
                )
            except Exception as error:
                logger.exception("indexing book %s failed", book_id)
                return f"Indexing failed: {error}"
            tokens += embeddings.tokens
            cost = (
                None
                if cost is None or embeddings.cost_usd is None
                else cost + embeddings.cost_usd
            )
            with engine.begin() as connection:
                connection.execute(
                    update(books)
                    .where(books.c.id == book_id)
                    .values(
                        passages_indexed=start + len(batch),
                        embedding_vector_size=len(embeddings.vectors[0]),
                        embedding_tokens=tokens,
                        embedding_cost_usd=cost,
                    )
                )
    finally:
        client.close()
    return None


def run_one_job(
    engine: Engine, settings: Settings, indexing: Indexing | None = None
) -> bool:
    """Parse the book of the oldest queued job into passages, and index them.

    The book ends in `indexed`, or in `failed` with an error. Without `indexing`,
    the job uses the embedder that `settings` picks, and the standard retries.
    Returns False when no job was queued.
    """
    claimed = _claim(engine)
    if claimed is None:
        return False
    job_id, book_id = claimed
    with engine.connect() as connection:
        config = connection.execute(
            select(books.c.passage_target_tokens, books.c.passage_overlap_tokens).where(
                books.c.id == book_id
            )
        ).one()
    try:
        data = book_path(settings.file_store_dir, book_id).read_bytes()
        built = build_passages(read_chapters(data), *config)
        error = None if built else NO_TEXT
    except EpubError as epub_error:
        built, error = [], str(epub_error)
    except Exception:
        logger.exception("parsing book %s failed", book_id)
        built, error = [], UNEXPECTED_FAILURE
    if error is not None:
        _finish(engine, job_id, {"id": book_id, "status": "failed", "error": error})
        return True
    indexing = indexing or Indexing(make_embedder(settings))
    with engine.begin() as connection:
        connection.execute(delete(passages).where(passages.c.book_id == book_id))
        connection.execute(
            insert(passages),
            [
                {
                    "id": passage_id(book_id, passage.position),
                    "book_id": book_id,
                    "position": passage.position,
                    "text": passage.text,
                    "chapter_title": passage.chapter_title,
                    "section_title": passage.section_title,
                    "spine_index": passage.spine_index,
                    "first_paragraph": passage.first_paragraph,
                    "last_paragraph": passage.last_paragraph,
                }
                for passage in built
            ],
        )
        connection.execute(
            update(books)
            .where(books.c.id == book_id)
            .values(
                status="indexing",
                error=None,
                passages_indexed=0,
                passages_total=len(built),
                embedding_model=indexing.embedder.model,
                embedding_vector_size=None,
                bm25_method=BM25_METHOD,
                embedding_tokens=0,
                embedding_cost_usd=0.0,
            )
        )
    error = _index(engine, settings, indexing, book_id, built)
    _finish(
        engine,
        job_id,
        {"id": book_id, "status": "indexed"}
        if error is None
        else {"id": book_id, "status": "failed", "error": error},
    )
    return True


def _beat(engine: Engine, worker_id: str, stop: threading.Event) -> None:
    """Write a heartbeat every poll interval until `stop` is set."""
    while not stop.is_set():
        try:
            tick(engine, worker_id)
        except Exception:
            # A database outage must not stop the worker; the next tick retries.
            logger.exception("heartbeat failed")
        stop.wait(POLL_INTERVAL_SECONDS)


def run(
    engine: Engine, worker_id: str, stop: threading.Event, settings: Settings
) -> None:
    """Write heartbeats and run queued jobs until `stop` is set.

    The heartbeats come from their own thread, so a long job does not make the
    worker look dead.
    """
    beats = threading.Thread(target=_beat, args=(engine, worker_id, stop))
    beats.start()
    try:
        if requeued := requeue_interrupted_jobs(engine):
            logger.info("put %d interrupted jobs back in the queue", requeued)
    except Exception:
        logger.exception("requeue failed")
    while not stop.is_set():
        try:
            if run_one_job(engine, settings):
                continue
        except Exception:
            logger.exception("job failed")
        stop.wait(POLL_INTERVAL_SECONDS)
    beats.join()


def main() -> None:
    """Run the worker until it gets SIGTERM or SIGINT."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env()
    engine = create_engine(settings.database_url)
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("got %s, stopping", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = socket.gethostname()
    logger.info("worker %s started", worker_id)
    run(engine, worker_id, stop, settings)
    engine.dispose()
    logger.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
