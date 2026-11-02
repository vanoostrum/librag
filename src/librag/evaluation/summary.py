# Copyright (C) 2026 Theo van Oostrum
"""The summary of an answer report: grades, evidence checks and Ragas, per model.

Ragas agreement is the Spearman correlation of faithfulness with the citation
grade, and of answer relevancy with the quality grade, over graded answers.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from librag.evaluation.grades import CITATION_GRADES, CITATION_LABELS, graded

CITATION_VALUES = {"wrong": 0.0, "partly": 0.5, "correct": 1.0}


def _ranks(values: Sequence[float]) -> list[float]:
    """Return the rank of each value, from 1; tied values share their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for i in order[start : end + 1]:
            ranks[i] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Return the Spearman correlation of `xs` and `ys`, from -1 to 1.

    None when there are fewer than 2 pairs, or when either side has no spread.
    """
    if len(xs) != len(ys):
        msg = "spearman needs as many xs as ys"
        raise ValueError(msg)
    if len(xs) < 2:  # noqa: PLR2004
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ragas(answer: Mapping[str, Any], name: str) -> float | None:
    ragas = answer.get("ragas") or {}
    value = ragas.get(name)
    return None if value is None else float(value)


def model_summary(
    answers: Sequence[Mapping[str, Any]],
    grades: Mapping[str, Mapping[str, Any]],
    report: str,
) -> dict[str, Any]:
    """Return the summary of one model's `answers`, with their `grades`."""
    found = [(answer, graded(grades, answer, report)) for answer in answers]
    quality = [
        (answer, g.grade["quality"])
        for answer, g in found
        if g.grade is not None and g.grade.get("quality") is not None
    ]
    citations = [
        (answer, g.grade["citations"])
        for answer, g in found
        if g.grade is not None and g.grade.get("citations") is not None
    ]
    faithfulness = [v for a in answers if (v := _ragas(a, "faithfulness")) is not None]
    relevancy = [v for a in answers if (v := _ragas(a, "answer_relevancy")) is not None]
    faith_pairs = [
        (f, CITATION_VALUES[grade])
        for answer, grade in citations
        if (f := _ragas(answer, "faithfulness")) is not None
    ]
    relevancy_pairs = [
        (r, float(grade))
        for answer, grade in quality
        if (r := _ragas(answer, "answer_relevancy")) is not None
    ]
    return {
        "answers": len(answers),
        "ungraded": sum(1 for _, g in found if g.needs_grade),
        "carried_over": sum(1 for _, g in found if g.carried_over),
        "quality_mean": _mean([float(grade) for _, grade in quality]),
        "quality_graded": len(quality),
        "citations": {
            name: (
                sum(1 for _, grade in citations if grade == name) / len(citations)
                if citations
                else None
            )
            for name in CITATION_GRADES
        },
        "citations_graded": len(citations),
        "evidence_pass_rate": _mean(
            [1.0 if a["evidence"]["passed"] else 0.0 for a in answers]
        ),
        "faithfulness_mean": _mean(faithfulness),
        "answer_relevancy_mean": _mean(relevancy),
        "agreement": {
            "faithfulness_vs_citations": spearman(
                [x for x, _ in faith_pairs], [y for _, y in faith_pairs]
            ),
            "faithfulness_pairs": len(faith_pairs),
            "relevancy_vs_quality": spearman(
                [x for x, _ in relevancy_pairs], [y for _, y in relevancy_pairs]
            ),
            "relevancy_pairs": len(relevancy_pairs),
        },
    }


def summary(
    report: Mapping[str, Any], grades: Mapping[str, Mapping[str, Any]], name: str
) -> dict[str, dict[str, Any]]:
    """Return the summary of each model in `report`, named `name`, in run order."""
    models = dict.fromkeys(answer["model"] for answer in report["answers"])
    return {
        model: model_summary(
            [a for a in report["answers"] if a["model"] == model], grades, name
        )
        for model in models
    }


def _number(value: float | None, digits: int = 2) -> str:
    return "none" if value is None else f"{value:.{digits}f}"


def _share(value: float | None) -> str:
    return "none" if value is None else f"{value:.0%}"


def text(name: str, summaries: Mapping[str, Mapping[str, Any]]) -> str:
    """Return the summary for the terminal: one block per model."""
    lines = [f"Answer evaluation: {name}"]
    for model, s in summaries.items():
        agreement = s["agreement"]
        shares = ", ".join(
            f"{CITATION_LABELS[g].lower()} {_share(s['citations'][g])}"
            for g in CITATION_GRADES
        )
        lines += [
            "",
            model,
            (
                f"  answers              {s['answers']} ({s['ungraded']} still to "
                f"grade, {s['carried_over']} carried over)"
            ),
            (
                f"  quality, mean (1-5)  {_number(s['quality_mean'])} over "
                f"{s['quality_graded']} graded"
            ),
            f"  citations            {shares} over {s['citations_graded']} graded",
            f"  evidence check       {_share(s['evidence_pass_rate'])} passed",
            f"  Ragas faithfulness   {_number(s['faithfulness_mean'])} mean",
            f"  Ragas relevancy      {_number(s['answer_relevancy_mean'])} mean",
            (
                "  Ragas agreement      faithfulness ~ citations "
                f"{_number(agreement['faithfulness_vs_citations'])} "
                f"(n={agreement['faithfulness_pairs']}), relevancy ~ quality "
                f"{_number(agreement['relevancy_vs_quality'])} "
                f"(n={agreement['relevancy_pairs']})"
            ),
        ]
    return "\n".join(lines)
