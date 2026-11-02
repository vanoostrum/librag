# Copyright (C) 2026 Theo van Oostrum
"""The evaluation set loader and the quote matcher, called directly.

Both take many input combinations, so they get unit tests (see CLAUDE.md).
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from librag.evaluation.evalset import (
    EvalSetError,
    Evidence,
    contains,
    fold,
    load,
    missing_quotes,
    parse,
)

VALID: dict[str, Any] = {
    "books": {
        "pride": {"gutenberg": 1342, "title": "Pride and Prejudice"},
        "dracula": {"gutenberg": 345, "title": "Dracula"},
    },
    "questions": [
        {
            "id": "f1",
            "type": "factual",
            "question": "Who wrote to Jonathan?",
            "evidence": [{"book": "dracula", "quote": "My friend.—Welcome."}],
            "books": ["dracula"],
        },
        {
            "id": "x1",
            "type": "cross-book",
            "question": "Which letters matter?",
            "evidence": [
                {"book": "dracula", "quote": "My friend."},
                {"book": "pride", "quote": "She read it."},
            ],
            "authors": ["Jane Austen", "Bram Stoker"],
        },
        {"id": "n1", "type": "negative", "question": "Who won the war?"},
    ],
}


def _with(index: int, **fields: object) -> dict[str, Any]:
    """Return VALID with fields of question `index` set; None removes a field."""
    data = copy.deepcopy(VALID)
    for name, value in fields.items():
        if value is None:
            data["questions"][index].pop(name, None)
        else:
            data["questions"][index][name] = value
    return data


def test_valid_set_loads_with_filters_and_evidence() -> None:
    """A valid set gives its books and questions, with filters and quotes."""
    evalset = parse(VALID)
    assert evalset.books["pride"].gutenberg == 1342  # noqa: PLR2004
    first, cross, negative = evalset.questions
    assert first.evidence == (Evidence("dracula", "My friend.—Welcome."),)
    assert first.books == ("dracula",)
    assert first.authors == ()
    assert cross.authors == ("Jane Austen", "Bram Stoker")
    assert negative.evidence == ()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_with(0, question=None), "question f1: missing field 'question'"),
        (_with(0, type=None), "question f1: missing field 'type'"),
        (_with(0, evidence=None), "question f1: missing field 'evidence'"),
        (_with(0, question="  "), "question f1: 'question' must be a non-empty"),
        (_with(0, type="trivia"), "question f1: unknown type 'trivia'"),
        (
            _with(
                1,
                evidence=[
                    {"book": "pride", "quote": "a"},
                    {"book": "pride", "quote": "b"},
                ],
            ),
            "question x1: a cross-book question needs quotes from at least 2 books",
        ),
        (
            _with(2, evidence=[{"book": "pride", "quote": "a"}]),
            "question n1: a negative question has no evidence quotes",
        ),
        (_with(0, evidence=[]), "question f1: a factual question needs at least one"),
        (
            _with(0, evidence=[{"book": "emma", "quote": "a"}]),
            "question f1: evidence names unknown book 'emma'",
        ),
        (
            _with(0, evidence=[{"book": "pride"}]),
            "question f1 evidence: missing field 'quote'",
        ),
        (_with(0, evidence=["a quote"]), "question f1: 'evidence' must be a list"),
        (_with(0, evidence="a quote"), "question f1: 'evidence' must be a list"),
        (_with(0, books=["emma"]), "question f1: 'books' names unknown book 'emma'"),
        (_with(0, authors="Bram Stoker"), "question f1: 'authors' must be a list"),
        (_with(0, id=None), "a question has no 'id'"),
        (_with(1, id="f1"), "question f1: the ID is used twice"),
    ],
)
def test_invalid_question_is_refused_by_id(data: dict[str, Any], message: str) -> None:
    """Each fault in a question raises an error that names the question."""
    with pytest.raises(EvalSetError) as error:
        parse(data)
    assert str(error.value).startswith(message), str(error.value)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"questions": VALID["questions"]}, "the set needs a [books.<key>] table"),
        ({"books": VALID["books"]}, "the set needs at least one [[questions]]"),
        ({"books": VALID["books"], "questions": ["x"]}, "each [[questions]] entry"),
        ({"books": {"pride": "x"}, "questions": []}, "book pride: must be a table"),
        (
            {"books": {"pride": {"title": "P"}}, "questions": []},
            "book pride: 'gutenberg' must be",
        ),
        (
            {"books": {"pride": {"gutenberg": True, "title": "P"}}, "questions": []},
            "book pride: 'gutenberg' must be",
        ),
        (
            {"books": {"pride": {"gutenberg": 1342}}, "questions": []},
            "book pride: missing field 'title'",
        ),
    ],
)
def test_invalid_set_is_refused(data: dict[str, Any], message: str) -> None:
    """A set without books or questions, or with a bad book, is refused."""
    with pytest.raises(EvalSetError) as error:
        parse(data)
    assert str(error.value).startswith(message), str(error.value)


def test_load_reads_toml_and_names_a_syntax_error(tmp_path: Path) -> None:
    """`load` reads a TOML file, and names the file when it is not TOML."""
    path = tmp_path / "set.toml"
    path.write_text(
        '[books.pride]\ngutenberg = 1342\ntitle = "Pride and Prejudice"\n'
        '[[questions]]\nid = "n1"\ntype = "negative"\nquestion = "Why?"\n',
        encoding="utf-8",
    )
    assert [q.id for q in load(path).questions] == ["n1"]
    path.write_text("not = = toml", encoding="utf-8")
    with pytest.raises(EvalSetError, match=r"set\.toml is not valid TOML"):
        load(path)


@pytest.mark.parametrize(
    ("text", "quote", "found"),
    [
        ("It is a truth universally acknowledged.", "a truth universally", True),
        ("IT IS A TRUTH", "it is a truth", True),
        ("a  truth\n universally", "a truth universally", True),
        ("\u201cDon\u2019t,\u201d she said\u2014quietly.", "don't she said", True),
        ("the _first_ letter", "the first letter", True),
        ("Café au lait", "CAFÉ AU", True),
        ("a truth universally", "a truth acknowledged", False),
        # Whole words only: "art" is not found inside "heart".
        ("my heart is heavy", "art is heavy", False),
        ("", "anything", False),
    ],
)
def test_contains_folds_case_whitespace_and_punctuation(
    text: str, quote: str, *, found: bool
) -> None:
    """A quote matches when its folded words appear in the folded text."""
    assert contains(text, quote) is found


def test_fold_keeps_letters_and_digits_only() -> None:
    """Folding lowercases and turns every other character into one space."""
    assert fold("  Chapter 3:  “Mr. Darcy!” ") == "chapter 3 mr darcy"


def test_missing_quotes_lists_quotes_that_no_passage_of_their_book_holds() -> None:
    """A quote counts as present only in a passage of its own book."""
    evalset = parse(VALID)
    passages = {
        "dracula": ["My friend. Welcome to my house!", "Nothing here."],
        # The pride quote is in a dracula passage only, so it is missing.
        "pride": ["Another text."],
    }
    passages["dracula"].append("She read it.")
    assert missing_quotes(evalset, passages) == [
        ("x1", Evidence("pride", "She read it.")),
    ]
