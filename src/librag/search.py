# Copyright (C) 2026 Theo van Oostrum
"""Retrieval: rank the passages of the indexed books for a search query.

Qdrant runs each stage (ADR 0003): a dense search, a BM25 search, and their
reciprocal rank fusion (RRF) through prefetch. Each stage is its own request,
so the response can show each stage's passages, scores and time.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models
from sqlalchemy import Engine, select

from librag.db import books
from librag.embeddings import Embedder
from librag.index import BM25, BM25_METHOD, DENSE, collection_name
from librag.settings import Settings

STAGES = ("dense", "bm25", "fusion")


@dataclass(frozen=True)
class SearchRequest:
    """A search query, its limits, and the books and authors it searches in.

    A limit of None takes the value from the settings. An empty or missing
    filter searches all indexed books.
    """

    query: str
    top_k: int | None = None
    dense_k: int | None = None
    bm25_k: int | None = None
    book_ids: Sequence[str] = ()
    authors: Sequence[str] = ()


def _searchable_book_ids(engine: Engine, request: SearchRequest) -> list[str]:
    """Return the indexed books that match the request's filters."""
    query = select(books.c.id).where(books.c.status == "indexed")
    if request.book_ids:
        query = query.where(books.c.id.in_(request.book_ids))
    if request.authors:
        query = query.where(books.c.author.in_(request.authors))
    with engine.connect() as connection:
        return list(connection.scalars(query))


def _timed(
    run: Callable[[], list[models.ScoredPoint]],
) -> tuple[list[models.ScoredPoint], float]:
    """Return what `run` returns, and how long it took in milliseconds."""
    start = time.perf_counter()
    points = run()
    return points, round((time.perf_counter() - start) * 1000, 3)


def _stage(points: list[models.ScoredPoint], time_ms: float) -> dict[str, Any]:
    return {
        "passages": [
            {"passage_id": str(point.id), "rank": rank, "score": point.score}
            for rank, point in enumerate(points, start=1)
        ],
        "time_ms": time_ms,
    }


def _result(rank: int, point: models.ScoredPoint) -> dict[str, Any]:
    payload = point.payload or {}
    return {
        "rank": rank,
        "passage_id": str(point.id),
        "book_id": payload["book_id"],
        "title": payload["title"],
        "author": payload["author"],
        "chapter": payload["chapter_title"],
        "section": payload["section_title"],
        "text": payload["text"],
        "score": point.score,
    }


def search(
    engine: Engine,
    settings: Settings,
    embedder: Embedder,
    client: QdrantClient,
    request: SearchRequest,
) -> dict[str, Any]:
    """Return the top passages for `request`, with each retrieval stage.

    Only books in `indexed` are searched, so a book that is still indexing
    never shows partial results.
    """
    top_k = request.top_k or settings.search_top_k
    dense_k = request.dense_k or settings.dense_top_k
    bm25_k = request.bm25_k or settings.bm25_top_k
    body: dict[str, Any] = {
        "query": request.query,
        "results": [],
        "stages": {stage: _stage([], 0.0) for stage in STAGES},
        "settings": {
            "top_k": top_k,
            "dense_k": dense_k,
            "bm25_k": bm25_k,
            "embedding_model": embedder.model,
        },
    }
    book_ids = _searchable_book_ids(engine, request)
    collection = collection_name(settings.qdrant_collection_prefix, embedder.model)
    # Books indexed with another embedding model are not in this collection.
    if not book_ids or not client.collection_exists(collection):
        return body

    [vector] = embedder.embed([request.query]).vectors
    document = models.Document(text=request.query, model=BM25_METHOD)
    only_books = models.Filter(
        must=[models.FieldCondition(key="book_id", match=models.MatchAny(any=book_ids))]
    )
    dense, dense_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                query=vector,
                using=DENSE,
                limit=dense_k,
                query_filter=only_books,
                with_payload=False,
            ).points
        )
    )
    bm25, bm25_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                query=document,
                using=BM25,
                limit=bm25_k,
                query_filter=only_books,
                with_payload=False,
            ).points
        )
    )
    fusion, fusion_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                prefetch=[
                    models.Prefetch(
                        query=vector, using=DENSE, limit=dense_k, filter=only_books
                    ),
                    models.Prefetch(
                        query=document, using=BM25, limit=bm25_k, filter=only_books
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                # Every candidate of both stages, so the fusion stage shows them all.
                limit=dense_k + bm25_k,
                with_payload=True,
            ).points
        )
    )
    body["stages"] = {
        "dense": _stage(dense, dense_ms),
        "bm25": _stage(bm25, bm25_ms),
        "fusion": _stage(fusion, fusion_ms),
    }
    body["results"] = [
        _result(rank, point) for rank, point in enumerate(fusion[:top_k], start=1)
    ]
    return body
