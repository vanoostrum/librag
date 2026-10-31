# Copyright (C) 2026 Theo van Oostrum
"""Embedders turn passage texts into dense vectors: LiteLLM, or an in-process fake."""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from librag.settings import Settings

if TYPE_CHECKING:
    from litellm.types.utils import EmbeddingResponse

FAKE_MODEL = "fake"
FAKE_VECTOR_SIZE = 256
WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Embeddings:
    """The vectors of a batch of texts, and what embedding them cost."""

    vectors: list[list[float]]
    tokens: int
    # None when LiteLLM does not know the model's price.
    cost_usd: float | None


class Embedder(Protocol):
    """Embeds texts with one model."""

    @property
    def model(self) -> str:
        """The model name, as LiteLLM knows it, or `fake`."""
        ...

    def embed(self, texts: list[str]) -> Embeddings:
        """Return one vector per text, in the same order."""
        ...


def _hashed_vector(words: list[str]) -> list[float]:
    vector = [0.0] * FAKE_VECTOR_SIZE
    for word in words:
        digest = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % FAKE_VECTOR_SIZE] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


class FakeEmbedder:
    """A deterministic embedder that needs no network (ADR 0005).

    It hashes each word into one of 256 dimensions and normalizes the vector,
    so texts that share words are similar. A token is a word, and it costs 0.
    """

    model = FAKE_MODEL

    def embed(self, texts: list[str]) -> Embeddings:
        """Return the hashed word vector of each text."""
        words = [WORD.findall(text.lower()) or [text] for text in texts]
        return Embeddings(
            vectors=[_hashed_vector(text_words) for text_words in words],
            tokens=sum(len(text_words) for text_words in words),
            cost_usd=0.0,
        )


@dataclass(frozen=True)
class LiteLlmEmbedder:
    """Embeds through an embedding API with LiteLLM (ADR 0002)."""

    model: str

    def embed(self, texts: list[str]) -> Embeddings:
        """Return the API's vectors, the tokens it counted and LiteLLM's cost."""
        # Imported here, so the fake providers never load LiteLLM.
        import litellm  # noqa: PLC0415

        # Without `aembedding`, LiteLLM answers synchronously.
        response = cast(
            "EmbeddingResponse", litellm.embedding(model=self.model, input=texts)
        )
        vectors = [item["embedding"] for item in response.data]
        try:
            cost = float(litellm.completion_cost(completion_response=response))
        except Exception:  # noqa: BLE001 - LiteLLM raises any error for an unknown price
            cost = None
        usage = response.usage
        return Embeddings(
            vectors=vectors, tokens=usage.prompt_tokens if usage else 0, cost_usd=cost
        )


def make_embedder(settings: Settings) -> Embedder:
    """Return the fake embedder, or the LiteLLM one for the configured model."""
    if settings.ai_providers == "fake":
        return FakeEmbedder()
    return LiteLlmEmbedder(settings.embedding_model)
