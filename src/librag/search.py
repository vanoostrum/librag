# Copyright (C) 2026 Theo van Oostrum
"""Retrieval: select the context from the passages of the indexed books for a query.

Qdrant runs the first stages (ADR 0003): a dense search, a BM25 search, and
their reciprocal rank fusion (RRF) through prefetch. Each stage is its own
request, so the response can show each stage's passages, scores and time. A
reranker then scores the fused candidates, and the context is the best of them
that fit a count and a token budget.
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
from librag.passages import count_tokens
from librag.rerank import Reranker
from librag.settings import Settings

STAGES = ("dense", "bm25", "fusion", "rerank")


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
    fusion_k: int | None = None
    token_budget: int | None = None
    rerank: bool = True
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


def _timed[T](run: Callable[[], T]) -> tuple[T, float]:
    """Return what `run` returns, and how long it took in milliseconds."""
    start = time.perf_counter()
    value = run()
    return value, round((time.perf_counter() - start) * 1000, 3)


def _stage(scored: Sequence[tuple[str, float]], time_ms: float) -> dict[str, Any]:
    return {
        "passages": [
            {"passage_id": passage, "rank": rank, "score": score}
            for rank, (passage, score) in enumerate(scored, start=1)
        ],
        "time_ms": time_ms,
    }


def _scored(points: list[models.ScoredPoint]) -> list[tuple[str, float]]:
    return [(str(point.id), point.score) for point in points]


@dataclass(frozen=True)
class _Candidate:
    """A fused passage, with its rerank score once the reranker has scored it."""

    point: models.ScoredPoint
    rerank_score: float | None = None

    @property
    def score(self) -> float:
        """The score that ranks the candidate: rerank's, or else fusion's."""
        return self.point.score if self.rerank_score is None else self.rerank_score


def _rerank(
    reranker: Reranker, query: str, fusion: list[models.ScoredPoint]
) -> list[_Candidate]:
    """Return the fused candidates by rerank score; a tie keeps the fusion order."""
    texts = [(point.payload or {})["text"] for point in fusion]
    scores = reranker.score(query, texts) if fusion else []
    candidates = [
        _Candidate(point, score) for point, score in zip(fusion, scores, strict=True)
    ]
    # sorted is stable, so equal scores keep their fusion order.
    return sorted(candidates, key=lambda candidate: -candidate.score)


def _select(
    candidates: list[_Candidate], top_k: int, token_budget: int
) -> list[_Candidate]:
    """Return the first `top_k` candidates, in order, that fit in `token_budget`.

    A candidate that does not fit the remaining budget is skipped, and a later
    one that fits is still added.
    """
    context: list[_Candidate] = []
    remaining = token_budget
    for candidate in candidates:
        if len(context) == top_k:
            break
        tokens = count_tokens((candidate.point.payload or {})["text"])
        if tokens <= remaining:
            context.append(candidate)
            remaining -= tokens
    return context


def _result(rank: int, candidate: _Candidate) -> dict[str, Any]:
    point = candidate.point
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
        "score": candidate.score,
        "fusion_score": point.score,
        "rerank_score": candidate.rerank_score,
    }


@dataclass(frozen=True)
class Searcher:
    """What search reads from: the database, Qdrant, and the models and settings."""

    engine: Engine
    settings: Settings
    embedder: Embedder
    reranker: Reranker
    client: QdrantClient


def search(searcher: Searcher, request: SearchRequest) -> dict[str, Any]:
    """Return the context for `request`, with each retrieval stage.

    `results` is the context: the fused candidates, reranked unless the
    request turns reranking off, then cut to `top_k` passages within
    `token_budget` tokens. Only books in `indexed` are searched, so a book
    that is still indexing never shows partial results.
    """
    engine, settings, embedder, reranker, client = (
        searcher.engine,
        searcher.settings,
        searcher.embedder,
        searcher.reranker,
        searcher.client,
    )
    top_k = request.top_k or settings.search_top_k
    dense_k = request.dense_k or settings.dense_top_k
    bm25_k = request.bm25_k or settings.bm25_top_k
    fusion_k = request.fusion_k or settings.fusion_top_k
    token_budget = request.token_budget or settings.context_token_budget
    body: dict[str, Any] = {
        "query": request.query,
        "results": [],
        "stages": {stage: _stage([], 0.0) for stage in STAGES},
        "settings": {
            "top_k": top_k,
            "dense_k": dense_k,
            "bm25_k": bm25_k,
            "fusion_k": fusion_k,
            "token_budget": token_budget,
            "rerank": request.rerank,
            "embedding_model": embedder.model,
            "reranker_model": reranker.model,
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
                limit=fusion_k,
                with_payload=True,
            ).points
        )
    )
    if request.rerank:
        ranked, rerank_ms = _timed(lambda: _rerank(reranker, request.query, fusion))
        reranked = [(str(c.point.id), c.score) for c in ranked]
    else:
        ranked, rerank_ms, reranked = [_Candidate(point) for point in fusion], 0.0, []
    body["stages"] = {
        "dense": _stage(_scored(dense), dense_ms),
        "bm25": _stage(_scored(bm25), bm25_ms),
        "fusion": _stage(_scored(fusion), fusion_ms),
        "rerank": _stage(reranked, rerank_ms),
    }
    context = _select(ranked, top_k, token_budget)
    body["results"] = [
        _result(rank, candidate) for rank, candidate in enumerate(context, start=1)
    ]
    return body
