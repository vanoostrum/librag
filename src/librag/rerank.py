# Copyright (C) 2026 Theo van Oostrum
"""Rerankers score how well each passage answers a query: a CrossEncoder, or a fake."""

import importlib
import re
import threading
from typing import Any, Protocol

from librag.settings import Settings

FAKE_MODEL = "fake"
WORD = re.compile(r"\w+")


class Reranker(Protocol):
    """Scores passages against a query with one model. A higher score is better."""

    @property
    def model(self) -> str:
        """The model name, as Hugging Face knows it, or `fake`."""
        ...

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Return one score per text, in the same order."""
        ...


class FakeReranker:
    """A deterministic reranker that needs no model or network (ADR 0005).

    A passage scores the share of the query's distinct words that it contains.
    """

    model = FAKE_MODEL

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Return the share of query words in each text, from 0 to 1."""
        query_words = set(WORD.findall(query.lower()))
        if not query_words:
            return [0.0] * len(texts)
        return [
            len(query_words & set(WORD.findall(text.lower()))) / len(query_words)
            for text in texts
        ]


class CrossEncoderReranker:
    """Scores with a local sentence-transformers CrossEncoder (ADR 0002).

    The model loads on first use and stays in memory. It needs the `rerank`
    extra, which the Docker image installs together with the model.
    """

    def __init__(self, model: str) -> None:
        """Remember the model; loading it waits until the first search."""
        self.model = model
        self._encoder: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:  # noqa: ANN401 - the extra is not installed for ty
        with self._lock:
            if self._encoder is None:
                # Imported here, so the fake providers and `checks` need no PyTorch.
                module = importlib.import_module("sentence_transformers")
                self._encoder = module.CrossEncoder(self.model)
            return self._encoder

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Return the CrossEncoder's score of each (query, text) pair."""
        scores = self._load().predict([(query, text) for text in texts])
        return [float(score) for score in scores]


def make_reranker(settings: Settings) -> Reranker:
    """Return the fake reranker, or the CrossEncoder of the configured model."""
    if settings.ai_providers == "fake":
        return FakeReranker()
    return CrossEncoderReranker(settings.reranker_model)
