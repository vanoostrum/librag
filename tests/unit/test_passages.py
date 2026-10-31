# Copyright (C) 2026 Theo van Oostrum
"""The passage builder. No route shows passage text yet, and packing has many cases.

These tests count a word as one token, so the sizes are easy to read.
"""

from librag.epub import Chapter, Paragraph
from librag.passages import Passage, build_passages, count_tokens, passage_id


def words(n: int, word: str = "word") -> str:
    """Return `n` words, which the tests count as `n` tokens."""
    return " ".join([word] * n)


def by_words(text: str) -> int:
    """Count one token per word."""
    return len(text.split())


def chapter(*texts: str, spine_index: int = 0, title: str = "One") -> Chapter:
    """Return a chapter with one paragraph per text, outside any section."""
    return Chapter(
        spine_index=spine_index,
        title=title,
        paragraphs=tuple(
            Paragraph(index=n, text=text, section=None) for n, text in enumerate(texts)
        ),
    )


def spans(built: list[Passage]) -> list[tuple[int, int, int]]:
    """Return (spine index, first paragraph, last paragraph) of each passage."""
    return [(p.spine_index, p.first_paragraph, p.last_paragraph) for p in built]


def test_packs_whole_paragraphs_up_to_the_target() -> None:
    """Paragraphs are packed while the passage stays within the target."""
    texts = [words(4, f"p{n}") for n in range(5)]
    built = build_passages([chapter(*texts)], 10, 0, by_words)
    assert spans(built) == [(0, 0, 1), (0, 2, 3), (0, 4, 4)]
    assert built[0].text == f"{texts[0]}\n\n{texts[1]}"
    assert [p.position for p in built] == [0, 1, 2]


def test_a_passage_can_fill_the_target_exactly() -> None:
    """A passage of exactly the target size takes the paragraph."""
    built = build_passages([chapter(words(5), words(5))], 10, 0, by_words)
    assert spans(built) == [(0, 0, 1)]


def test_passages_overlap_by_whole_paragraphs() -> None:
    """The next passage starts with the last paragraphs that fit in the overlap."""
    texts = [words(4, f"p{n}") for n in range(4)]
    built = build_passages([chapter(*texts)], 10, 4, by_words)
    assert spans(built) == [(0, 0, 1), (0, 1, 2), (0, 2, 3)]
    assert built[1].text == f"{texts[1]}\n\n{texts[2]}"


def test_overlap_takes_no_paragraph_larger_than_the_overlap() -> None:
    """A last paragraph over the overlap size is not repeated."""
    built = build_passages([chapter(words(6), words(6))], 10, 4, by_words)
    assert spans(built) == [(0, 0, 0), (0, 1, 1)]


def test_overlap_gives_way_to_the_next_paragraph() -> None:
    """Overlap is dropped when it and the next paragraph do not fit the target."""
    built = build_passages([chapter(words(3), words(3), words(8))], 10, 4, by_words)
    assert spans(built) == [(0, 0, 1), (0, 2, 2)]


def test_passages_never_cross_a_chapter() -> None:
    """Each chapter starts a new passage, without overlap from the one before."""
    chapters = [
        chapter(words(2, "a"), spine_index=0, title="One"),
        chapter(words(2, "b"), spine_index=3, title="Two"),
    ]
    built = build_passages(chapters, 10, 4, by_words)
    assert spans(built) == [(0, 0, 0), (3, 0, 0)]
    assert [p.chapter_title for p in built] == ["One", "Two"]
    assert [p.position for p in built] == [0, 1]


def test_long_paragraph_splits_at_sentence_boundaries() -> None:
    """A paragraph over the target is split between sentences."""
    text = "One two three four. Five six seven eight! Nine ten eleven twelve?"
    built = build_passages([chapter(text)], 10, 0, by_words)
    assert [p.text for p in built] == [
        "One two three four. Five six seven eight!",
        "Nine ten eleven twelve?",
    ]
    assert spans(built) == [(0, 0, 0), (0, 0, 0)]


def test_sentence_pieces_overlap_and_join_with_spaces() -> None:
    """Pieces of one paragraph overlap like paragraphs, and join with a space."""
    text = "A b c. D e f. G h i. J k l."
    built = build_passages([chapter(text)], 6, 3, by_words)
    assert [p.text for p in built] == [
        "A b c. D e f.",
        "D e f. G h i.",
        "G h i. J k l.",
    ]


def test_a_sentence_over_the_target_stays_whole() -> None:
    """A single sentence over the target is one passage; it is not cut."""
    built = build_passages([chapter(words(12))], 10, 0, by_words)
    assert [by_words(p.text) for p in built] == [12]


def test_passage_has_the_section_of_its_first_paragraph() -> None:
    """A passage's section is the nearest section heading above its start."""
    paragraphs = (
        Paragraph(index=0, text=words(4), section=None),
        Paragraph(index=1, text=words(4), section="Part A"),
        Paragraph(index=2, text=words(4), section="Part B"),
    )
    chapters = [Chapter(spine_index=0, title="One", paragraphs=paragraphs)]
    built = build_passages(chapters, 8, 0, by_words)
    assert [p.section_title for p in built] == [None, "Part B"]


def test_chapter_without_paragraphs_gives_no_passages() -> None:
    """An empty chapter adds no passage."""
    assert build_passages([chapter()], 10, 0, by_words) == []


def test_count_tokens_uses_cl100k_base() -> None:
    """The default token counter is tiktoken cl100k_base."""
    assert count_tokens("hello world") == 2  # noqa: PLR2004
    built = build_passages([chapter("hello world", "hello world")], 4, 0)
    assert spans(built) == [(0, 0, 1)]


def test_passage_ids_derive_from_book_and_position() -> None:
    """The same book and position give the same ID; another position another one."""
    assert passage_id("abc", 0) == passage_id("abc", 0)
    assert passage_id("abc", 0) != passage_id("abc", 1)
    assert passage_id("abc", 0) != passage_id("abd", 0)


def test_overlap_can_repeat_the_whole_passage_before() -> None:
    """When the whole passage fits the overlap, it is repeated as far as it fits."""
    built = build_passages([chapter(words(3), words(3), words(5))], 10, 8, by_words)
    assert spans(built) == [(0, 0, 1), (0, 1, 2)]
