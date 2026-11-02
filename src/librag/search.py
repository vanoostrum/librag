# Copyright (C) 2026 Theo van Oostrum
"""Retrieval: select the context from the passages of the indexed books for a query.

Qdrant runs the first stages (ADR 0003): a dense search, a BM25 search, and
their reciprocal rank fusion (RRF) through prefetch. Each stage is its own
request, so the response can show each stage's passages, scores and time. A
reranker then scores the fused candidates, and the context is the best of them
that fit a count and a token budget.

A search query split into sub-questions runs those stages once per
sub-question. A reciprocal rank fusion over their fusion lists gives the fused
candidates, and the reranker scores them against the search query.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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
# The stages that run once per sub-question.
QUERY_STAGES = ("dense", "bm25", "fusion")
# The constant of the reciprocal rank fusion across sub-questions: 1 / (k + rank).
RRF_K = 60


@dataclass(frozen=True)
class SearchRequest:
    """A search query, its limits, and the books and authors it searches in.

    A limit of None takes the value from the settings. An empty or missing
    filter searches all indexed books. `queries` are the sub-questions that
    `query` was split into; without them, `query` is the only one.
    """

    query: str
    queries: Sequence[str] = ()
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
    return _ranked_stage(
        [(passage, rank, score) for rank, (passage, score) in enumerate(scored, 1)],
        time_ms,
    )


def _ranked_stage(
    ranked: Sequence[tuple[str, int, float]], time_ms: float
) -> dict[str, Any]:
    return {
        "passages": [
            {"passage_id": passage, "rank": rank, "score": score}
            for passage, rank, score in ranked
        ],
        "time_ms": time_ms,
    }


def _scored(points: list[models.ScoredPoint]) -> list[tuple[str, float]]:
    return [(str(point.id), point.score) for point in points]


def _best_ranks(
    lists: Sequence[list[models.ScoredPoint]],
) -> list[tuple[str, int, float]]:
    """Return each passage of `lists` once, with its best rank and its score there.

    The passages come by that rank; equal ranks keep the order of the lists.
    """
    best: dict[str, tuple[int, float]] = {}
    for points in lists:
        for rank, point in enumerate(points, start=1):
            passage = str(point.id)
            if passage not in best or rank < best[passage][0]:
                best[passage] = (rank, point.score)
    ordered = sorted(best.items(), key=lambda item: item[1][0])
    return [(passage, rank, score) for passage, (rank, score) in ordered]


def _fuse(
    lists: Sequence[list[models.ScoredPoint]], limit: int
) -> list[models.ScoredPoint]:
    """Return the first `limit` passages of the reciprocal rank fusion of `lists`.

    Each passage's score is its fusion score; equal scores keep first-seen order.
    """
    scores: dict[str, float] = {}
    points: dict[str, models.ScoredPoint] = {}
    for fused in lists:
        for rank, point in enumerate(fused, start=1):
            passage = str(point.id)
            scores[passage] = scores.get(passage, 0.0) + 1 / (RRF_K + rank)
            points.setdefault(passage, point)
    ordered = sorted(scores, key=lambda passage: -scores[passage])[:limit]
    return [
        points[passage].model_copy(update={"score": scores[passage]})
        for passage in ordered
    ]


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
        "context": payload.get("context"),
        "score": candidate.score,
        "fusion_score": point.score,
        "rerank_score": candidate.rerank_score,
    }


@dataclass(frozen=True)
class Retrieval:
    """What a search found: its response body, and each staged passage's payload."""

    body: dict[str, Any]
    payloads: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def candidates(self, *, with_context: bool = False) -> list[dict[str, Any]]:
        """Return the book and text of each passage in any stage.

        The fused candidates come first, in fusion order, then the passages
        that only dense or BM25 found, in the order of those stages. Each has
        `found_by`: the IDs of the queries whose fusion list holds it. With
        `with_context`, each also has its context line, or None.
        """
        ids = [
            passage["passage_id"]
            for stage in ("fusion", "dense", "bm25")
            for passage in self.body["stages"][stage]["passages"]
        ]
        fused_by = [
            (
                query["id"],
                {item["passage_id"] for item in query["stages"]["fusion"]["passages"]},
            )
            for query in self.body["queries"]
        ]
        return [
            {
                "passage_id": passage,
                "book_id": self.payloads[passage]["book_id"],
                "title": self.payloads[passage]["title"],
                "chapter": self.payloads[passage]["chapter_title"],
                "section": self.payloads[passage]["section_title"],
                "text": self.payloads[passage]["text"],
                "found_by": [query for query, fused in fused_by if passage in fused],
                **(
                    {"context": self.payloads[passage].get("context")}
                    if with_context
                    else {}
                ),
            }
            for passage in dict.fromkeys(ids)
        ]


@dataclass(frozen=True)
class Searcher:
    """What search reads from: the database, Qdrant, and the models and settings."""

    engine: Engine
    settings: Settings
    embedder: Embedder
    reranker: Reranker
    client: QdrantClient


@dataclass(frozen=True)
class _Searched:
    """The dense, BM25 and fusion passages of one query, and each stage's time."""

    dense: list[models.ScoredPoint]
    bm25: list[models.ScoredPoint]
    fusion: list[models.ScoredPoint]
    times: tuple[float, float, float]

    def stages(self) -> dict[str, Any]:
        lists = (self.dense, self.bm25, self.fusion)
        return {
            stage: _stage(_scored(points), time_ms)
            for stage, points, time_ms in zip(
                QUERY_STAGES, lists, self.times, strict=True
            )
        }


@dataclass(frozen=True)
class _Limits:
    """How many passages each stage keeps, and the books it searches in."""

    dense_k: int
    bm25_k: int
    fusion_k: int
    only_books: models.Filter


def _search(
    client: QdrantClient,
    collection: str,
    limits: _Limits,
    query: str,
    vector: list[float],
) -> _Searched:
    """Run the dense, BM25 and fusion stages of one query in Qdrant."""
    document = models.Document(text=query, model=BM25_METHOD)
    only_books = limits.only_books
    dense, dense_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                query=vector,
                using=DENSE,
                limit=limits.dense_k,
                query_filter=only_books,
                with_payload=True,
            ).points
        )
    )
    bm25, bm25_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                query=document,
                using=BM25,
                limit=limits.bm25_k,
                query_filter=only_books,
                with_payload=True,
            ).points
        )
    )
    fusion, fusion_ms = _timed(
        lambda: (
            client.query_points(
                collection,
                prefetch=[
                    models.Prefetch(
                        query=vector,
                        using=DENSE,
                        limit=limits.dense_k,
                        filter=only_books,
                    ),
                    models.Prefetch(
                        query=document,
                        using=BM25,
                        limit=limits.bm25_k,
                        filter=only_books,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limits.fusion_k,
                with_payload=True,
            ).points
        )
    )
    return _Searched(dense, bm25, fusion, (dense_ms, bm25_ms, fusion_ms))


def _combined(
    searched: Sequence[_Searched], fusion: list[models.ScoredPoint], fuse_ms: float
) -> dict[str, Any]:
    """Return the dense, BM25 and fusion stages over all queries.

    One query's stages are its own. Over several, dense and BM25 list each
    passage once at its best rank, and `fusion` fused the queries' fusion
    lists. Each time is the sum over the queries.
    """
    if len(searched) == 1:
        return searched[0].stages()
    dense_ms, bm25_ms, fusion_ms = (
        sum(times) for times in zip(*(s.times for s in searched), strict=True)
    )
    return {
        "dense": _ranked_stage(_best_ranks([s.dense for s in searched]), dense_ms),
        "bm25": _ranked_stage(_best_ranks([s.bm25 for s in searched]), bm25_ms),
        "fusion": _stage(_scored(fusion), round(fusion_ms + fuse_ms, 3)),
    }


def _query_bodies(
    texts: Sequence[str], searched: Sequence[_Searched] = ()
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"Q{n}",
            "text": text,
            "stages": (
                searched[n - 1].stages()
                if searched
                else {stage: _stage([], 0.0) for stage in QUERY_STAGES}
            ),
        }
        for n, text in enumerate(texts, start=1)
    ]


def retrieve(searcher: Searcher, request: SearchRequest) -> Retrieval:
    """Return the context for `request`, with each retrieval stage.

    `results` is the context: the fused candidates, reranked unless the
    request turns reranking off, then cut to `top_k` passages within
    `token_budget` tokens. Only books in `indexed` are searched, so a book
    that is still indexing never shows partial results. `queries` lists each
    query that was searched, with its own dense, BM25 and fusion stages.
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
    texts = list(request.queries) or [request.query]
    body: dict[str, Any] = {
        "query": request.query,
        "queries": _query_bodies(texts),
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
        return Retrieval(body)

    only_books = models.Filter(
        must=[models.FieldCondition(key="book_id", match=models.MatchAny(any=book_ids))]
    )
    limits = _Limits(dense_k, bm25_k, fusion_k, only_books)
    vectors = embedder.embed(texts).vectors
    searched = [
        _search(client, collection, limits, text, vector)
        for text, vector in zip(texts, vectors, strict=True)
    ]
    fusion, fuse_ms = (
        (searched[0].fusion, 0.0)
        if len(searched) == 1
        else _timed(lambda: _fuse([s.fusion for s in searched], fusion_k))
    )
    if request.rerank:
        ranked, rerank_ms = _timed(lambda: _rerank(reranker, request.query, fusion))
        reranked = [(str(c.point.id), c.score) for c in ranked]
    else:
        ranked, rerank_ms, reranked = [_Candidate(point) for point in fusion], 0.0, []
    body["queries"] = _query_bodies(texts, searched)
    body["stages"] = {
        **_combined(searched, fusion, fuse_ms),
        "rerank": _stage(reranked, rerank_ms),
    }
    context = _select(ranked, top_k, token_budget)
    body["results"] = [
        _result(rank, candidate) for rank, candidate in enumerate(context, start=1)
    ]
    staged = [point for s in searched for point in (*s.dense, *s.bm25, *s.fusion)]
    payloads = {str(point.id): point.payload or {} for point in staged}
    return Retrieval(body, payloads)
