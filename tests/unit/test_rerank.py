# Copyright (C) 2026 Theo van Oostrum
"""The live CrossEncoder reranker, with sentence-transformers replaced by a stub.

No request reaches the live reranker: the route tests use the fake, and the
`rerank` extra is not installed outside the Docker image (ADR 0005).
"""

import sys
import types

import pytest

from librag.rerank import CrossEncoderReranker, make_reranker
from librag.settings import Settings


class StubCrossEncoder:
    """Scores a pair by the length of its text, and counts how often it loads."""

    loads = 0

    def __init__(self, model: str) -> None:
        """Record the load."""
        StubCrossEncoder.loads += 1
        self.model = model

    def predict(self, pairs: list[tuple[str, str]]) -> list[int]:
        """Return the length of each pair's text."""
        return [len(text) for _query, text in pairs]


@pytest.fixture
def stub_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a stub `sentence_transformers` module."""
    module = types.ModuleType("sentence_transformers")
    module.CrossEncoder = StubCrossEncoder  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    StubCrossEncoder.loads = 0


@pytest.mark.usefixtures("stub_sentence_transformers")
def test_live_reranker_loads_the_model_once_and_scores_each_text() -> None:
    """The CrossEncoder loads on first use, once, and scores texts in order."""
    reranker = make_reranker(Settings(reranker_model="some/cross-encoder"))
    assert isinstance(reranker, CrossEncoderReranker)
    assert reranker.model == "some/cross-encoder"
    assert StubCrossEncoder.loads == 0
    assert reranker.score("q", ["abc", "a"]) == [3.0, 1.0]
    assert reranker.score("q", ["ab"]) == [2.0]
    assert StubCrossEncoder.loads == 1
