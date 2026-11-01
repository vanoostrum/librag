# Copyright (C) 2026 Theo van Oostrum
"""The Qdrant collection of each embedding model, and the passage points in it."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

DENSE = "dense"
BM25 = "bm25"
# Qdrant computes the BM25 sparse vectors itself, from the text (decision 1).
BM25_METHOD = "qdrant/bm25"
QDRANT_TIMEOUT_SECONDS = 30
KEYWORD_FIELDS = ("book_id", "author")


def qdrant_client(qdrant_url: str) -> QdrantClient:
    """Return a client for the Qdrant at `qdrant_url`.

    With `cloud_inference`, the client sends BM25 documents to the server to
    embed, instead of embedding them itself with fastembed.
    """
    return QdrantClient(
        url=qdrant_url, timeout=QDRANT_TIMEOUT_SECONDS, cloud_inference=True
    )


def collection_name(prefix: str, model: str) -> str:
    """Return the collection of `model`: `passages_openai_text-embedding-3-small`."""
    return f"{prefix}_{re.sub(r'[^A-Za-z0-9_-]+', '_', model)}"


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    """Create the collection `name` with a dense and a BM25 vector, if it is missing."""
    if client.collection_exists(name):
        return
    client.create_collection(
        name,
        vectors_config={
            DENSE: models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={
            BM25: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    for field in KEYWORD_FIELDS:
        client.create_payload_index(
            name, field, field_schema=models.PayloadSchemaType.KEYWORD
        )


@dataclass(frozen=True)
class Point:
    """A passage as Qdrant stores it: its ID, indexed text, vector and payload."""

    id: str
    text: str
    vector: list[float]
    payload: dict[str, object]


def upsert(client: QdrantClient, name: str, points: Sequence[Point]) -> None:
    """Write `points` to the collection `name`, and wait until Qdrant has them."""
    client.upsert(
        name,
        points=[
            models.PointStruct(
                id=point.id,
                vector={
                    DENSE: point.vector,
                    BM25: models.Document(text=point.text, model=BM25_METHOD),
                },
                payload=point.payload,
            )
            for point in points
        ],
        wait=True,
    )


def delete_book_points(client: QdrantClient, prefix: str, book_id: str) -> None:
    """Delete the points of `book_id` from the collection of every embedding model."""
    book = models.Filter(
        must=[
            models.FieldCondition(key="book_id", match=models.MatchValue(value=book_id))
        ]
    )
    for collection in client.get_collections().collections:
        if collection.name.startswith(f"{prefix}_"):
            client.delete(
                collection.name,
                points_selector=models.FilterSelector(filter=book),
                wait=True,
            )
