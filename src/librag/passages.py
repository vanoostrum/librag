# Copyright (C) 2026 Theo van Oostrum
"""Build a book's passages from its chapters: whole paragraphs, packed to a size."""

import itertools
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache

import tiktoken

from librag.epub import Chapter

TOKENIZER = "cl100k_base"
# Passage IDs are UUIDs, so Qdrant can use them as point IDs.
PASSAGE_ID_NAMESPACE = uuid.UUID("6f1d3c2a-6b8e-4f43-9a51-7d1c2b9e0a10")
# A sentence ends at . ! ? or an ellipsis, then any closing quotes or brackets.
SENTENCE_END = re.compile("(?<=[.!?\u2026])[\"'\u201d\u2019)\\]]*\\s+")

CountTokens = Callable[[str], int]


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(TOKENIZER)


def count_tokens(text: str) -> int:
    """Return the number of `cl100k_base` tokens in `text`."""
    return len(_encoding().encode(text, disallowed_special=()))


def passage_id(book_id: str, position: int) -> str:
    """Return the ID of the passage at `position` in the book `book_id`."""
    return str(uuid.uuid5(PASSAGE_ID_NAMESPACE, f"{book_id}/{position}"))


@dataclass(frozen=True)
class Passage:
    """A passage's text and its source location in the book."""

    position: int
    text: str
    chapter_title: str
    section_title: str | None
    spine_index: int
    first_paragraph: int
    last_paragraph: int


@dataclass(frozen=True)
class _Unit:
    """A whole paragraph, or one sentence of a paragraph over the target."""

    paragraph: int
    section: str | None
    text: str
    tokens: int


def _units(chapter: Chapter, target: int, count: CountTokens) -> Iterable[_Unit]:
    for paragraph in chapter.paragraphs:
        tokens = count(paragraph.text)
        if tokens <= target:
            yield _Unit(paragraph.index, paragraph.section, paragraph.text, tokens)
            continue
        # Paragraph text is whitespace-collapsed, so no sentence is empty.
        for sentence in SENTENCE_END.split(paragraph.text):
            yield _Unit(paragraph.index, paragraph.section, sentence, count(sentence))


def _join(units: list[_Unit]) -> str:
    """Join units: sentences of one paragraph with a space, paragraphs with a line."""
    text = units[0].text
    for before, unit in itertools.pairwise(units):
        text += (" " if unit.paragraph == before.paragraph else "\n\n") + unit.text
    return text


def _overlap(units: list[_Unit], overlap: int) -> list[_Unit]:
    """Return the longest tail of `units` whose tokens fit in `overlap`."""
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total + unit.tokens > overlap:
            break
        tail.insert(0, unit)
        total += unit.tokens
    return tail


def _pack(units: Iterable[_Unit], target: int, overlap: int) -> list[list[_Unit]]:
    """Pack units into groups up to `target` tokens, each starting with an overlap."""
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    for unit in units:
        if current and sum(u.tokens for u in current) + unit.tokens > target:
            groups.append(current)
            current = _overlap(current, overlap)
            while current and sum(u.tokens for u in current) + unit.tokens > target:
                current.pop(0)
        current.append(unit)
    if current:
        groups.append(current)
    return groups


def build_passages(
    chapters: Iterable[Chapter],
    target_tokens: int,
    overlap_tokens: int,
    count: CountTokens = count_tokens,
) -> list[Passage]:
    """Return the passages of `chapters`, numbered in book order.

    A passage packs whole paragraphs up to `target_tokens`, and starts with the
    last whole paragraphs of the passage before it that fit in `overlap_tokens`.
    A paragraph over the target is split into sentences, which pack the same way.
    A passage never crosses a chapter.
    """
    built: list[Passage] = []
    for chapter in chapters:
        for group in _pack(
            _units(chapter, target_tokens, count), target_tokens, overlap_tokens
        ):
            built.append(
                Passage(
                    position=len(built),
                    text=_join(group),
                    chapter_title=chapter.title,
                    section_title=group[0].section,
                    spine_index=chapter.spine_index,
                    first_paragraph=group[0].paragraph,
                    last_paragraph=group[-1].paragraph,
                )
            )
    return built
