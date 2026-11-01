# Copyright (C) 2026 Theo van Oostrum
"""The citation check and the answer format.

Many combinations of parts and citation numbers, which are slow to reach one
by one through POST /api/chat; tests/integration/test_chat.py covers the route.
"""

import pytest

from librag.chat import AnswerFormatError, Part, check_citations, parse_answer
from librag.prompts import NO_PASSAGE


@pytest.mark.parametrize(
    ("parts", "context_size", "expected"),
    [
        pytest.param(
            [
                Part("book", "A.", (1, 2)),
                Part("synthesis", "S."),
                Part("general", "G."),
            ],
            2,
            [
                Part("book", "A.", (1, 2)),
                Part("synthesis", "S."),
                Part("general", "G."),
            ],
            id="valid answer is kept",
        ),
        pytest.param(
            [Part("book", "A.", (0, 1, 3, -1))],
            2,
            [Part("book", "A.", (1,))],
            id="numbers outside 1 to N are removed",
        ),
        pytest.param(
            [Part("book", "A.", (2, 1, 2))],
            2,
            [Part("book", "A.", (2, 1))],
            id="repeated number is cited once",
        ),
        pytest.param(
            [Part("book", "A.", (3,)), Part("general", "G.")],
            2,
            [Part("general", "A. G.")],
            id="claim without a valid citation moves to general, in order",
        ),
        pytest.param(
            [Part("book", "A."), Part("book", "B.", (1,))],
            1,
            [Part("book", "B.", (1,)), Part("general", "A.")],
            id="claim without citations moves to general",
        ),
        pytest.param(
            [Part("general", "G.", (1,))],
            1,
            [Part("general", "G.")],
            id="general part cites nothing",
        ),
        pytest.param(
            [Part("synthesis", "S.", (1, 5))],
            1,
            [Part("synthesis", "S.", (1,))],
            id="synthesis keeps its valid citations",
        ),
        pytest.param(
            [
                Part("general", "G."),
                Part("synthesis", "S1."),
                Part("book", "A.", (1,)),
                Part("synthesis", "S2.", (1,)),
            ],
            1,
            [
                Part("book", "A.", (1,)),
                Part("synthesis", "S1. S2.", (1,)),
                Part("general", "G."),
            ],
            id="parts come in the order book, synthesis, general",
        ),
        pytest.param(
            [Part("book", "  ", (1,)), Part("synthesis", ""), Part("general", " G. ")],
            1,
            [Part("general", "G.")],
            id="part without text is left out",
        ),
        pytest.param(
            [Part("book", "A.", (1,)), Part("synthesis", "S.")],
            0,
            [Part("general", f"{NO_PASSAGE} A. S.")],
            id="empty context: one general part with the no-passage sentence",
        ),
        pytest.param(
            [Part("general", f"{NO_PASSAGE} G.")],
            0,
            [Part("general", f"{NO_PASSAGE} G.")],
            id="empty context: the sentence is not repeated",
        ),
        pytest.param(
            [],
            0,
            [Part("general", NO_PASSAGE)],
            id="empty context and no parts",
        ),
        pytest.param([], 3, [], id="no parts"),
    ],
)
def test_check_citations(
    parts: list[Part], context_size: int, expected: list[Part]
) -> None:
    """Only citations to the context remain, and uncited claims are general."""
    assert check_citations(parts, context_size) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            '{"parts": [{"kind": "book", "text": "A.", "citations": [1, 2]}]}',
            [Part("book", "A.", (1, 2))],
            id="answer",
        ),
        pytest.param(
            '```json\n{"parts": [{"kind": "general", "text": "G."}]}\n```',
            [Part("general", "G.")],
            id="code fence and no citations",
        ),
        pytest.param(
            '{"parts": [{"kind": "book", "text": "A.", "citations": [1, "2", true]}]}',
            [Part("book", "A.", (1,))],
            id="citation that is not a number is ignored",
        ),
        pytest.param('{"parts": []}', [], id="no parts"),
    ],
)
def test_parse_answer(text: str, expected: list[Part]) -> None:
    """The LLM's JSON reply becomes parts."""
    assert parse_answer(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Here is the answer.",
        "[]",
        '{"answer": "A."}',
        '{"parts": ["A."]}',
        '{"parts": [{"kind": "claim", "text": "A."}]}',
        '{"parts": [{"kind": "book", "text": 1}]}',
        '{"parts": [{"kind": "book", "text": "A.", "citations": 1}]}',
    ],
)
def test_parse_answer_refuses_another_shape(text: str) -> None:
    """A reply that is not the answer format raises AnswerFormatError."""
    with pytest.raises(AnswerFormatError):
        parse_answer(text)
