# Copyright (C) 2026 Theo van Oostrum
"""The enrichers and the chapter rebuild: what no route can reach or show well.

No route test reaches a real provider, so LiteLLM's request is checked here,
with its `mock_response`, which builds a real response without a network call.
"""

from typing import Any

import litellm
import pytest

from librag.enrichment import (
    MAX_CONTEXT_TOKENS,
    LiteLlmEnricher,
    chapter_texts,
    make_enricher,
)
from librag.epub import read_chapters
from librag.passages import Passage, build_passages, count_tokens
from librag.settings import Settings
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

MODEL = "anthropic/claude-haiku-5-5"
PASSAGE = Passage(0, "The keeper lit the lamp.", "The Light", None, 3, 0, 0)
CHAPTER = "The storm came in.\n\nThe keeper lit the lamp."


def mock_completion(
    monkeypatch: pytest.MonkeyPatch, response: str
) -> list[dict[str, Any]]:
    """Make `litellm.completion` answer with `response`, offline; record requests."""
    requests: list[dict[str, Any]] = []
    completion = litellm.completion

    def answer(**kwargs: Any) -> Any:  # noqa: ANN401 - LiteLLM's own signature
        requests.append(kwargs)
        return completion(**kwargs, mock_response=response)

    monkeypatch.setattr(litellm, "completion", answer)
    return requests


def test_live_enricher_sends_the_chapter_as_a_cached_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chapter is a cached block, then the passage; the model is the setting's."""
    requests = mock_completion(monkeypatch, "The keeper of the Light, in the storm.")
    enrichment = LiteLlmEnricher(MODEL).enrich(CHAPTER, PASSAGE)
    [request] = requests
    assert request["model"] == MODEL
    system, user = request["messages"]
    assert system["role"] == "system"
    assert "who and what the passage is about" in system["content"]
    chapter, passage = user["content"]
    assert chapter == {
        "type": "text",
        "text": f"<chapter>\nChapter: The Light\n\n{CHAPTER}\n</chapter>",
        "cache_control": {"type": "ephemeral"},
    }
    assert passage == {
        "type": "text",
        "text": "<passage>\nThe keeper lit the lamp.\n</passage>",
    }
    assert enrichment.context == "The keeper of the Light, in the storm."


def test_live_enricher_reads_tokens_and_cost_from_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tokens are the provider's, and the cost is LiteLLM's."""
    mock_completion(monkeypatch, "The keeper of the Light.")
    enrichment = LiteLlmEnricher(MODEL).enrich(CHAPTER, PASSAGE)
    assert enrichment.input_tokens > 0
    assert enrichment.output_tokens > 0
    assert enrichment.cost_usd is not None
    assert enrichment.cost_usd > 0


def test_live_enricher_without_a_price_has_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """For a model that LiteLLM has no price for, the cost is None, not 0."""
    mock_completion(monkeypatch, "The keeper.")
    enrichment = LiteLlmEnricher("openai/no-such-model").enrich(CHAPTER, PASSAGE)
    assert enrichment.cost_usd is None


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("  The keeper,\n\nin the storm.  ", "The keeper, in the storm."),
        (" \n ", ""),
    ],
)
def test_live_enricher_puts_the_line_on_one_line(
    monkeypatch: pytest.MonkeyPatch, reply: str, expected: str
) -> None:
    """Whitespace and line breaks in the reply become single spaces."""
    mock_completion(monkeypatch, reply)
    assert LiteLlmEnricher(MODEL).enrich(CHAPTER, PASSAGE).context == expected


def test_live_enricher_cuts_a_long_line_to_80_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reply over 80 tokens is cut to its first 80."""
    long = " ".join(f"word{n}" for n in range(200))
    mock_completion(monkeypatch, long)
    context = LiteLlmEnricher(MODEL).enrich(CHAPTER, PASSAGE).context
    assert count_tokens(context) == MAX_CONTEXT_TOKENS
    assert long.startswith(context)


def test_make_enricher_with_live_providers() -> None:
    """With the live providers: no enricher when off, LiteLLM's on the model when on.

    The route tests cover the fake providers.
    """
    assert make_enricher(Settings(ai_providers="live")) is None
    assert make_enricher(Settings(enrichment=True)) == LiteLlmEnricher(MODEL)


def _chapter(*texts: str) -> FixtureChapter:
    return FixtureChapter(paragraphs(*texts))


@pytest.mark.parametrize(
    ("target", "overlap"),
    [(40, 0), (40, 15), (60, 30), (25, 20), (350, 50)],
)
def test_chapter_texts_rebuild_each_chapter_without_the_overlap(
    target: int, overlap: int
) -> None:
    """The chapter text from the passages is its paragraphs, each once, in order."""
    first = [
        f"Paragraph {n} of the first chapter tells of the keeper and the lamp."
        for n in range(8)
    ]
    second = [
        "A long paragraph. " + " ".join(f"Sentence {n} is short." for n in range(12)),
        "The last paragraph of the second chapter.",
    ]
    book = FixtureBook(chapters=(_chapter(*first), _chapter(*second)))
    chapters = read_chapters(make_epub(book))
    built = build_passages(chapters, target, overlap)
    texts = chapter_texts(built)
    assert list(texts) == [chapter.spine_index for chapter in chapters]
    for chapter in chapters:
        rebuilt = texts[chapter.spine_index]
        expected = [paragraph.text for paragraph in chapter.paragraphs]
        # A paragraph split into sentences comes back as one line per piece.
        assert rebuilt.replace("\n\n", " ") == " ".join(expected)
