# Copyright (C) 2026 Theo van Oostrum
"""The enrichment migration on a database with data: no request runs a migration."""

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from sqlalchemy import Engine, MetaData, Table, create_engine, insert, inspect, select

from librag.db import alembic_config

BOOK: dict[str, object] = {
    "id": "b1",
    "title": "Sea Stories",
    "author": "Ada Writer",
    "content_sha256": "0" * 64,
    "status": "indexed",
    "passages_indexed": 1,
    "passages_total": 1,
    "passage_target_tokens": 350,
    "passage_overlap_tokens": 50,
    "tokenizer": "cl100k_base",
    "uploaded_at": datetime(2026, 11, 1, tzinfo=UTC).replace(tzinfo=None),
    "embedding_model": "fake",
    "embedding_tokens": 12,
    "embedding_cost_usd": 0.5,
}
PASSAGE: dict[str, object] = {
    "id": "p1",
    "book_id": "b1",
    "position": 0,
    "text": "The keeper lit the lamp.",
    "chapter_title": "Part 1",
    "spine_index": 0,
    "first_paragraph": 0,
    "last_paragraph": 0,
}


def _table(engine: Engine, name: str) -> Table:
    """Return the table `name` as the database has it now."""
    return Table(name, MetaData(), autoload_with=engine)


def _insert(engine: Engine, name: str, row: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(insert(_table(engine, name)).values(**row))


def _row(engine: Engine, name: str) -> dict[str, object]:
    with engine.connect() as connection:
        return dict(connection.execute(select(_table(engine, name))).mappings().one())


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_enrichment_migration_keeps_the_data_up_and_down(tmp_path: Path) -> None:
    """0006 adds the columns with no enrichment for existing books, and drops them."""
    url = f"sqlite:///{tmp_path / 'librag.db'}"
    config = alembic_config(url)
    command.upgrade(config, "0005")
    engine = create_engine(url)
    try:
        _insert(engine, "books", BOOK)
        _insert(engine, "passages", PASSAGE)
        book_before, passage_before = _row(engine, "books"), _row(engine, "passages")

        command.upgrade(config, "0006")
        book, passage = _row(engine, "books"), _row(engine, "passages")
        assert book == {
            **book_before,
            "enrichment_model": None,
            "enrichment_input_tokens": 0,
            "enrichment_output_tokens": 0,
            "enrichment_cost_usd": 0.0,
        }
        assert passage == {**passage_before, "context": None}

        command.downgrade(config, "0005")
        assert _row(engine, "books") == book_before
        assert _row(engine, "passages") == passage_before
        assert "context" not in _columns(engine, "passages")
        assert not {c for c in _columns(engine, "books") if c.startswith("enrich")}
    finally:
        engine.dispose()
