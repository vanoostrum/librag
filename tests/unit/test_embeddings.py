# Copyright (C) 2026 Theo van Oostrum
"""The embedders and collection names: many inputs that no route shows."""

import functools
import math

import litellm
import pytest

from librag.embeddings import FakeEmbedder, LiteLlmEmbedder, make_embedder
from librag.index import collection_name
from librag.settings import Settings


def cosine(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity of `a` and `b`."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


@pytest.mark.parametrize(
    ("text", "sharing", "other"),
    [
        ("the quiet library", "a quiet library at night", "running foxes jump"),
        ("Whale hunting", "the WHALE, hunting!", "tea and biscuits"),
        ("chapter one", "one chapter", "nothing alike here"),
    ],
)
def test_fake_rates_shared_words_as_similar(
    text: str, sharing: str, other: str
) -> None:
    """Texts that share words are closer than texts that share none."""
    a, b, c = FakeEmbedder().embed([text, sharing, other]).vectors
    assert cosine(a, b) > cosine(a, c)
    assert cosine(a, c) == pytest.approx(0.0, abs=0.3)


@pytest.mark.parametrize("text", ["the quiet library", "", "…", "naïve café"])
def test_fake_is_deterministic_and_normalized(text: str) -> None:
    """The same text always gives the same unit vector of 256 dimensions."""
    first = FakeEmbedder().embed([text]).vectors[0]
    assert FakeEmbedder().embed([text]).vectors[0] == first
    assert len(first) == 256  # noqa: PLR2004
    assert math.sqrt(sum(x * x for x in first)) == pytest.approx(1.0)


def test_fake_counts_words_and_costs_nothing() -> None:
    """A token is a word, and the cost is 0."""
    embeddings = FakeEmbedder().embed(["one two three", "four"])
    assert (embeddings.tokens, embeddings.cost_usd) == (4, 0.0)


def test_live_embedder_reads_litellm_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The LiteLLM embedder returns LiteLLM's vector, tokens and cost.

    LiteLLM's `mock_response` builds a real response without a network call.
    """
    monkeypatch.setattr(
        litellm,
        "embedding",
        functools.partial(litellm.embedding, mock_response=[0.5, 0.25]),
    )
    embeddings = LiteLlmEmbedder("openai/text-embedding-3-small").embed(["hello"])
    assert embeddings.vectors == [[0.5, 0.25]]
    assert embeddings.tokens > 0
    assert embeddings.cost_usd is not None
    assert embeddings.cost_usd > 0


def test_live_embedder_without_a_price_has_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """For a model that LiteLLM cannot price, the cost is None."""
    monkeypatch.setattr(
        litellm,
        "embedding",
        functools.partial(litellm.embedding, mock_response=[0.5, 0.25]),
    )
    embeddings = LiteLlmEmbedder("openai/no-such-embedding-model").embed(["hello"])
    assert embeddings.cost_usd is None


def test_settings_pick_the_embedder() -> None:
    """`fake` picks the fake; `live` picks LiteLLM with the configured model."""
    assert isinstance(make_embedder(Settings(ai_providers="fake")), FakeEmbedder)
    live = make_embedder(Settings(embedding_model="openai/text-embedding-3-large"))
    assert live == LiteLlmEmbedder("openai/text-embedding-3-large")


@pytest.mark.parametrize(
    ("model", "name"),
    [
        ("openai/text-embedding-3-small", "passages_openai_text-embedding-3-small"),
        ("fake", "passages_fake"),
        ("azure/my deployment:v2", "passages_azure_my_deployment_v2"),
    ],
)
def test_collection_name_slugs_the_model(model: str, name: str) -> None:
    """Each model gets its own collection, with a name Qdrant accepts."""
    assert collection_name("passages", model) == name
