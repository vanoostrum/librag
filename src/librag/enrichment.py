# Copyright (C) 2026 Theo van Oostrum
"""Contextual enrichment: an LLM writes a context line for each passage (ADR 0005).

The context line says who and what the passage is about, in the book's own
terms. It is indexed with the passage, and kept apart from the passage's text.
"""

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from librag.llm import cost
from librag.passages import Passage, truncate_tokens
from librag.settings import Settings

FAKE_MODEL = "fake"
# The prompt asks for about 50 tokens; a longer line is cut to this many.
MAX_CONTEXT_TOKENS = 80
MAX_OUTPUT_TOKENS = 120
WORD = re.compile(r"\w+")
WHITESPACE = re.compile(r"\s+")

INSTRUCTIONS = """\
You help a search engine find passages of a book. You get a chapter of the book, \
then one passage of that chapter. Write one short sentence, at most 50 tokens, \
that says who and what the passage is about, in the book's own terms: the people, \
places and events it names or refers to. Write no commentary and no opinion. \
Reply with only that sentence.
"""


@dataclass(frozen=True)
class Enrichment:
    """A passage's context line, and what writing it cost."""

    context: str
    input_tokens: int
    output_tokens: int
    # None when LiteLLM does not know the model's price.
    cost_usd: float | None


class Enricher(Protocol):
    """Writes context lines with one model."""

    @property
    def model(self) -> str:
        """The model name, as LiteLLM knows it, or `fake`."""
        ...

    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Return the context line of `passage`, which is part of `chapter`."""
        ...


def one_line(text: str) -> str:
    """Return `text` on one line, at most `MAX_CONTEXT_TOKENS` tokens long."""
    return truncate_tokens(WHITESPACE.sub(" ", text).strip(), MAX_CONTEXT_TOKENS)


class FakeEnricher:
    """A deterministic enricher that needs no network (ADR 0005).

    Its line is `About <chapter heading>: <first five words>`, so tests can find
    it. A token is a word, and it costs 0.
    """

    model = FAKE_MODEL

    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Return the fake context line of `passage`."""
        first = " ".join(WORD.findall(passage.text)[:5])
        context = f"About {passage.chapter_title}: {first}"
        return Enrichment(
            context=context,
            input_tokens=len(WORD.findall(chapter)) + len(WORD.findall(passage.text)),
            output_tokens=len(WORD.findall(context)),
            cost_usd=0.0,
        )


def messages(chapter: str, passage: Passage) -> list[dict[str, Any]]:
    """Return the request's messages: the chapter as a cached block, then the passage.

    The chapter block is the same for every passage of the chapter, so the
    provider reads it from its prompt cache after the first call.
    """
    heading = f"Chapter: {passage.chapter_title}\n\n" if passage.chapter_title else ""
    return [
        {"role": "system", "content": INSTRUCTIONS},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"<chapter>\n{heading}{chapter}\n</chapter>",
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": f"<passage>\n{passage.text}\n</passage>"},
            ],
        },
    ]


@dataclass(frozen=True)
class LiteLlmEnricher:
    """Writes context lines through the provider's API with LiteLLM (ADR 0004)."""

    model: str

    def enrich(self, chapter: str, passage: Passage) -> Enrichment:
        """Return the model's line, cut to 80 tokens, its tokens and LiteLLM's cost."""
        # Imported here, so the fake providers never load LiteLLM.
        import litellm  # noqa: PLC0415

        response: Any = litellm.completion(
            model=self.model,
            messages=messages(chapter, passage),
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        usage = response.usage
        return Enrichment(
            context=one_line(response.choices[0].message.content or ""),
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=cost(litellm, self.model, response),
        )


def make_enricher(settings: Settings) -> Enricher | None:
    """Return the enricher that the settings pick, or None when enrichment is off."""
    if not settings.enrichment:
        return None
    if settings.ai_providers == "fake":
        return FakeEnricher()
    return LiteLlmEnricher(settings.enrichment_model)


def _without_overlap(before: str, text: str) -> str:
    """Return `text` without the start it repeats from the end of `before`.

    A passage starts with the last paragraphs or sentences of the passage
    before it, so the longest end of `before` that starts `text` is dropped.
    """
    for start in range(len(before)):
        tail = before[start:]
        rest = text[len(tail) :]
        # The overlap is whole paragraphs or sentences, so whitespace bounds it.
        if (
            (start == 0 or before[start - 1].isspace())
            and text.startswith(tail)
            and (not rest or rest[0].isspace())
        ):
            return rest.lstrip()
    return text


def chapter_texts(passages: Sequence[Passage]) -> dict[int, str]:
    """Return the text of each chapter, by spine index, rebuilt from its passages.

    The overlap that each passage repeats from the one before it is left out,
    so the stored passages give the chapter without a new parse.
    """
    texts: dict[int, str] = {}
    chapters: Iterable[tuple[int, Iterable[Passage]]] = itertools.groupby(
        passages, key=lambda passage: passage.spine_index
    )
    for spine_index, group in chapters:
        parts: list[str] = []
        before = ""
        for passage in group:
            # Each passage adds at least one unit after its overlap.
            parts.append(_without_overlap(before, passage.text))
            before = passage.text
        texts[spine_index] = "\n\n".join(parts)
    return texts
