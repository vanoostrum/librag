# Copyright (C) 2026 Theo van Oostrum
"""Grade carry-over, grade checks, the evidence check and the summary statistics.

These have many input combinations, so they are tested on the functions; the
route tests in tests/integration/test_answer_evaluation.py cover the flow.
"""

from typing import Any

import pytest

from librag.evaluation.answers import answer_hash, evidence_check
from librag.evaluation.evalset import Evidence, Question
from librag.evaluation.grades import GradeError, check_change, grade_key, graded
from librag.evaluation.summary import model_summary, spearman
from librag.evaluation.usage import missing_keys

ANSWER = {"question_id": "f1", "model": "openai/gpt-6.1-terra", "answer_hash": "abc"}
KEY = grade_key(ANSWER)


@pytest.mark.parametrize(
    ("grade", "carried", "needs"),
    [
        (None, False, True),
        ({"quality": 4, "citations": "correct", "report": "a.json"}, False, False),
        ({"quality": 4, "citations": "correct", "report": "old.json"}, True, False),
        ({"quality": 4, "citations": None, "report": "old.json"}, False, True),
        ({"quality": None, "citations": "wrong", "report": "a.json"}, False, True),
    ],
)
def test_graded_carries_over_only_a_complete_grade_from_another_report(
    grade: dict[str, Any] | None, *, carried: bool, needs: bool
) -> None:
    """A complete grade from another report is carried over; a partial one is not."""
    grades = {KEY: grade} if grade is not None else {}
    found = graded(grades, ANSWER, "a.json")
    assert found.carried_over is carried
    assert found.needs_grade is needs


def test_grade_of_another_answer_does_not_apply() -> None:
    """A grade keyed by another hash, model or question is not this answer's."""
    for other in (
        {**ANSWER, "answer_hash": "def"},
        {**ANSWER, "model": "anthropic/claude-sonnet-5-5"},
        {**ANSWER, "question_id": "f2"},
    ):
        grades = {grade_key(other): {"quality": 5, "citations": "correct"}}
        assert graded(grades, ANSWER, "a.json").grade is None


@pytest.mark.parametrize(
    ("change", "checked"),
    [
        ({"quality": 1}, {"quality": 1}),
        ({"quality": 5, "citations": "partly"}, {"quality": 5, "citations": "partly"}),
        ({"quality": None, "citations": None}, {"quality": None, "citations": None}),
        ({"notes": ""}, {"notes": ""}),
        ({}, {}),
    ],
)
def test_valid_grade_changes_pass(
    change: dict[str, Any], checked: dict[str, Any]
) -> None:
    """Quality 1 to 5, a citation grade, notes, or None to clear, are accepted."""
    assert check_change(change) == checked


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"quality": 0}, "quality"),
        ({"quality": 3.5}, "quality"),
        ({"quality": "4"}, "quality"),
        ({"quality": True}, "quality"),
        ({"citations": "partly correct"}, "citations"),
        ({"notes": 3}, "notes"),
        ({"report": "x"}, "report: not a grade field"),
    ],
)
def test_invalid_grade_changes_are_refused(
    change: dict[str, Any], message: str
) -> None:
    """A grade out of range, of the wrong type, or an unknown field is refused."""
    with pytest.raises(GradeError, match=message):
        check_change(change)


def _question(*evidence: Evidence) -> Question:
    kind = "factual" if evidence else "negative"
    return Question("q", kind, "Why?", tuple(evidence))


def _citation(n: int, book_id: str, text: str) -> dict[str, Any]:
    return {"n": n, "book_id": book_id, "passage_id": f"p{n}", "text": text}


BOOK = {"part": "part", "kind": "book", "text": "Claim.", "citations": [1]}
GENERAL = {"kind": "general", "text": "Not in the books.", "citations": []}
IDS = {"sea": "id-sea", "harbour": "id-harbour"}


@pytest.mark.parametrize(
    ("parts", "passed", "claims"),
    [([GENERAL], True, 0), ([BOOK, GENERAL], False, 1), ([], True, 0)],
)
def test_negative_question_passes_without_book_claims(
    parts: list[dict[str, Any]], *, passed: bool, claims: int
) -> None:
    """A negative question passes only when the answer makes no book claims."""
    check = evidence_check(_question(), parts, [], IDS)
    assert check == {"passed": passed, "book_claims": claims, "quotes": []}


def test_evidence_check_needs_each_quote_in_a_cited_passage_of_its_book() -> None:
    """A quote counts only in a cited passage of its own book, after folding."""
    question = _question(
        Evidence("sea", "the brass lamp"), Evidence("harbour", "coral reef")
    )
    citations = [
        _citation(1, "id-sea", "He polished THE brass-lamp."),
        # The right words, but in the other book.
        _citation(2, "id-sea", "a coral reef"),
    ]
    check = evidence_check(question, [BOOK], citations, IDS)
    assert check["passed"] is False
    assert [q["cited_in"] for q in check["quotes"]] == [[1], []]
    citations.append(_citation(3, "id-harbour", "The coral reef."))
    assert evidence_check(question, [BOOK], citations, IDS)["passed"] is True


def test_answer_hash_changes_with_text_or_cited_passage_only() -> None:
    """The hash follows the parts and the cited text, not other fields."""
    parts = [{"kind": "book", "text": "Claim.", "citations": [1]}]
    citations = [{"n": 1, "passage_id": "p1", "text": "Passage.", "chapter": "1"}]
    base = answer_hash(parts, citations)
    assert answer_hash(parts, [{**citations[0], "chapter": "2"}]) == base
    assert answer_hash([{**parts[0], "text": "Other."}], citations) != base
    assert answer_hash(parts, [{**citations[0], "text": "Other."}]) != base
    assert answer_hash(parts, [{**citations[0], "passage_id": "p2"}]) != base


@pytest.mark.parametrize(
    ("xs", "ys", "expected"),
    [
        ([1, 2, 3], [10, 20, 30], 1.0),
        ([1, 2, 3], [3, 2, 1], -1.0),
        ([1, 2, 3, 4], [1, 3, 2, 4], 0.8),
        # Ties share their mean rank.
        ([1, 1, 2], [1, 2, 3], 0.8660254),
        ([0.5], [1], None),
        ([], [], None),
        ([1, 1, 1], [1, 2, 3], None),
    ],
)
def test_spearman(xs: list[float], ys: list[float], expected: float | None) -> None:
    """Spearman's rho, with ties, and None without 2 pairs or without spread."""
    result = spearman(xs, ys)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_spearman_needs_pairs() -> None:
    """Lists of different lengths are a programming error."""
    with pytest.raises(ValueError, match="as many"):
        spearman([1, 2], [1])


def _answer(n: int, faith: float | None, relevancy: float | None) -> dict[str, Any]:
    return {
        "question_id": f"q{n}",
        "model": "m",
        "answer_hash": f"h{n}",
        "evidence": {"passed": n % 2 == 0},
        "ragas": None
        if faith is None and relevancy is None
        else {"faithfulness": faith, "answer_relevancy": relevancy},
    }


def test_model_summary_on_known_grades() -> None:
    """Means, shares, pass rate and agreement over the graded answers only."""
    answers = [
        _answer(1, 0.2, 0.3),
        _answer(2, 0.6, 0.5),
        _answer(3, 0.9, 0.9),
        _answer(4, None, None),
    ]
    grades = {
        "q1|m|h1": {"quality": 2, "citations": "wrong", "report": "r"},
        "q2|m|h2": {"quality": 3, "citations": "partly", "report": "old"},
        "q3|m|h3": {"quality": 5, "citations": "correct", "report": "r"},
        "q4|m|h4": {"quality": 4, "citations": None, "report": "r"},
    }
    s = model_summary(answers, grades, "r")
    assert s["answers"] == 4  # noqa: PLR2004
    assert s["ungraded"] == 1
    assert s["carried_over"] == 1
    assert s["quality_mean"] == pytest.approx(3.5)
    assert s["citations"] == pytest.approx(
        {"correct": 1 / 3, "partly": 1 / 3, "wrong": 1 / 3}
    )
    assert s["evidence_pass_rate"] == 0.5  # noqa: PLR2004
    assert s["faithfulness_mean"] == pytest.approx(1.7 / 3)
    assert s["agreement"]["faithfulness_vs_citations"] == pytest.approx(1.0)
    assert s["agreement"]["faithfulness_pairs"] == 3  # noqa: PLR2004
    assert s["agreement"]["relevancy_vs_quality"] == pytest.approx(1.0)


def test_model_summary_without_grades_or_ragas() -> None:
    """With nothing graded and no Ragas, the statistics are None, not zero."""
    s = model_summary([_answer(1, None, None)], {}, "r")
    assert s["quality_mean"] is None
    assert s["citations"] == {"correct": None, "partly": None, "wrong": None}
    assert s["faithfulness_mean"] is None
    assert s["agreement"]["relevancy_vs_quality"] is None


@pytest.mark.parametrize(
    ("models", "environ", "missing"),
    [
        (["openai/a", "anthropic/b"], {}, ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]),
        (["openai/a", "openai/b"], {"OPENAI_API_KEY": "k"}, []),
        (["gemini/a", "xai/b"], {"XAI_API_KEY": ""}, ["GEMINI_API_KEY", "XAI_API_KEY"]),
        (["ollama/local", "fake"], {}, []),
    ],
)
def test_missing_keys_by_provider(
    models: list[str], environ: dict[str, str], missing: list[str]
) -> None:
    """Each known provider needs its key once; an unknown provider needs none."""
    assert missing_keys(models, environ) == missing
