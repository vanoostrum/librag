# Copyright (C) 2026 Theo van Oostrum
"""Put the uploaded books of a verify run in the states of a Library gallery page.

The worker moves a book through `parsing` and `indexing` in a moment, so a
screenshot cannot catch those states. This sets the status, passage counts and
index configuration of the books, by title, to those of
`design/pages/library/<page>.html`. A book shown in progress gets a running
job, which the running worker leaves alone, so it does not show as interrupted.
A book set in progress without one is interrupted, as the reindex page shows.

Usage: uv run python .claude/skills/verify/scripts/library-states.py <db url> <page>
"""

import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, insert, select, update

from librag.db import books, ingestion_jobs

IN_PROGRESS = {"queued", "parsing", "indexing"}
OLD_MODEL = "openai/text-embedding-3-small"
DEFAULT = {
    "Thinking, Fast and Slow": {"status": "indexed", "done": 612, "total": 612},
    "Noise": {"status": "indexed", "done": 488, "total": 488},
    "The Black Swan": {"status": "indexing", "done": 386, "total": 612},
    "Meditations": {"status": "queued", "done": 0, "total": None},
}
STATES = {
    "default": DEFAULT,
    "delete-confirm": DEFAULT,
    "upload-error": {
        "Thinking, Fast and Slow": {"status": "indexed", "done": 612, "total": 612},
        "The Black Swan": {"status": "indexing", "done": 386, "total": 612},
        "Antifragile": {"status": "parsing", "done": 0, "total": None},
        "Meditations": {"status": "queued", "done": 0, "total": None},
    },
    # Run with LIBRAG_REINDEX_ENABLED=on. Antifragile is interrupted: it is left
    # in indexing with no job to finish it.
    "reindex": {
        "Thinking, Fast and Slow": {
            "status": "indexed",
            "done": 612,
            "total": 612,
            "embedding_model": OLD_MODEL,
        },
        "Noise": {
            "status": "indexed",
            "done": 488,
            "total": 488,
            "passage_target_tokens": 500,
        },
        "The Black Swan": {"status": "indexing", "done": 251, "total": 612},
        "Meditations": {"status": "indexed", "done": 203, "total": 203},
        "Antifragile": {
            "status": "indexing",
            "done": 120,
            "total": 300,
            "interrupted": True,
        },
    },
}


def main(database_url: str, page: str) -> None:
    """Set the books of `page` in the database at `database_url`."""
    engine = create_engine(database_url)
    now = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        for title, state in STATES[page].items():
            values = dict(state)
            done, total = values.pop("done"), values.pop("total")
            interrupted = values.pop("interrupted", False) is True
            book_id = connection.scalar(
                select(books.c.id).where(books.c.title == title)
            )
            changed = connection.execute(
                update(books)
                .where(books.c.id == book_id)
                .values(passages_indexed=done, passages_total=total, **values)
            ).rowcount
            if values["status"] in IN_PROGRESS and not interrupted:
                connection.execute(
                    insert(ingestion_jobs).values(
                        book_id=book_id,
                        status="running",
                        created_at=now,
                        started_at=now,
                    )
                )
            print(f"{title}: {values} {done}/{total} ({changed} row)")  # noqa: T201
    engine.dispose()


if __name__ == "__main__":
    main(*sys.argv[1:])
