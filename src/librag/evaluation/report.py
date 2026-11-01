# Copyright (C) 2026 Theo van Oostrum
"""The evaluation report: a table for the terminal, and the JSON report."""

from collections.abc import Mapping, Sequence
from typing import Any

from librag.evaluation.evalset import Evidence
from librag.evaluation.score import METRICS, STAGES, Scored

HEADERS = {"recall@5": "R@5", "recall@10": "R@10", "recall@20": "R@20", "mrr": "MRR"}


def _table(title: str, entry: Mapping[str, Any]) -> list[str]:
    lines = [f"{title} ({entry['questions']} questions)"]
    lines.append(f"  {'stage':<8}" + "".join(f"{HEADERS[m]:>7}" for m in METRICS))
    for stage in STAGES:
        values = entry["stages"][stage]
        lines.append(f"  {stage:<8}" + "".join(f"{values[m]:>7.3f}" for m in METRICS))
    return lines


def _score(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"


def table(
    result: Mapping[str, Any],
    scored: Sequence[Scored],
    missing: Sequence[tuple[str, Evidence]],
) -> str:
    """Return the report for the terminal: metrics, negatives, missing quotes."""
    lines = ["Retrieval evaluation", ""]
    if result["overall"]["stages"]:
        lines += _table("All questions with evidence", result["overall"])
    for kind, entry in result["by_type"].items():
        lines += ["", *_table(kind.capitalize(), entry)]
    negatives = [s for s in scored if not s.question.evidence]
    if negatives:
        lines += ["", "Negative questions: no book answers them; top rerank score"]
        lines += [
            f"  {s.question.id:<14} {_score(s.top_rerank_score):>8}  "
            f"{s.question.question}"
            for s in negatives
        ]
    if missing:
        lines += ["", "Evidence quotes that no passage contains (fix the set):"]
        lines += [
            f"  {question_id}: [{evidence.book}] {evidence.quote}"
            for question_id, evidence in missing
        ]
    return "\n".join(lines)


def report_json(
    result: Mapping[str, Any],
    scored: Sequence[Scored],
    missing: Sequence[tuple[str, Evidence]],
    run: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the JSON report: the run, the metrics, and each question's ranks."""
    return {
        **run,
        "metrics": result,
        "questions": [
            {
                "id": s.question.id,
                "type": s.question.type,
                "question": s.question.question,
                "first_relevant_rank": s.first_rank,
                "quotes": [
                    {"book": e.book, "quote": e.quote, "ranks": ranks}
                    for e, ranks in zip(s.question.evidence, s.quote_ranks, strict=True)
                ],
                "top_rerank_score": s.top_rerank_score,
            }
            for s in scored
        ],
        "missing_quotes": [
            {"question": question_id, "book": e.book, "quote": e.quote}
            for question_id, e in missing
        ],
    }
