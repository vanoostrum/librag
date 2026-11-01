# Copyright (C) 2026 Theo van Oostrum
"""Put the uploaded books of a verify run in the states of a Library gallery page.

The worker moves a book through `parsing` and `indexing` in a moment, so a
screenshot cannot catch those states. This sets the status and passage counts of
the books, by title, to those of `design/pages/library/<page>.html`.

Usage: uv run python .claude/skills/verify/scripts/library-states.py <db url> <page>
"""

import sys

from sqlalchemy import create_engine, update

from librag.db import books

STATES = {
    "default": {
        "Thinking, Fast and Slow": ("indexed", 612, 612),
        "Noise": ("indexed", 488, 488),
        "The Black Swan": ("indexing", 386, 612),
        "Meditations": ("queued", 0, None),
    },
    "upload-error": {
        "Thinking, Fast and Slow": ("indexed", 612, 612),
        "The Black Swan": ("indexing", 386, 612),
        "Antifragile": ("parsing", 0, None),
        "Meditations": ("queued", 0, None),
    },
}


def main(database_url: str, page: str) -> None:
    """Set the books of `page` in the database at `database_url`."""
    engine = create_engine(database_url)
    with engine.begin() as connection:
        for title, (status, indexed, total) in STATES[page].items():
            changed = connection.execute(
                update(books)
                .where(books.c.title == title)
                .values(status=status, passages_indexed=indexed, passages_total=total)
            ).rowcount
            print(f"{title}: {status} {indexed}/{total} ({changed} row)")  # noqa: T201
    engine.dispose()


if __name__ == "__main__":
    main(*sys.argv[1:])
