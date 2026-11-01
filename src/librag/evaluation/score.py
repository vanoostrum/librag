# Copyright (C) 2026 Theo van Oostrum
"""Score each retrieval stage on the evaluation set with ranx.

Each evidence quote counts as one relevant item. In a stage's ranking, the
first passage that holds a quote stands for that quote, so Recall@K is the
share of a question's quotes found in the top K passages, and MRR uses the
rank of the first passage that holds any quote. A passage that holds two new
quotes takes two places in the ranking; with quotes of one sentence or less,
that is rare.
"""

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from librag.evaluation.evalset import QUESTION_TYPES, Question, contains

STAGES = ("dense", "bm25", "fusion", "rerank")
METRICS = ("recall@5", "recall@10", "recall@20", "mrr")
EMPTY = "no-passage"


@dataclass(frozen=True)
class Scored:
    """One question's search: each quote's first rank, and the first relevant rank.

    `quote_ranks[i][stage]` is the rank of the first passage in `stage` that
    holds quote `i`, or None. `first_rank[stage]` is the best of those.
    """

    question: Question
    quote_ranks: tuple[dict[str, int | None], ...]
    first_rank: dict[str, int | None]
    top_rerank_score: float | None
    stage_docs: dict[str, dict[str, float]]


def _quotes_by_passage(
    question: Question, body: Mapping[str, Any], book_ids: Mapping[str, str]
) -> dict[str, list[int]]:
    """Return the indexes of the quotes that each candidate passage holds."""
    held: dict[str, list[int]] = {}
    for candidate in body["candidates"]:
        for index, evidence in enumerate(question.evidence):
            if candidate["book_id"] == book_ids[evidence.book] and contains(
                candidate["text"], evidence.quote
            ):
                held.setdefault(candidate["passage_id"], []).append(index)
    return held


def _no_ranks() -> dict[str, int | None]:
    ranks: dict[str, int | None] = {}
    for stage in STAGES:
        ranks[stage] = None
    return ranks


def score_question(
    question: Question, body: Mapping[str, Any], book_ids: Mapping[str, str]
) -> Scored:
    """Return the ranks of `question`'s quotes in each stage of its search `body`."""
    held = _quotes_by_passage(question, body, book_ids)
    quote_ranks = [_no_ranks() for _ in question.evidence]
    first_rank = _no_ranks()
    stage_docs: dict[str, dict[str, float]] = {}
    for stage in STAGES:
        passages = body["stages"][stage]["passages"]
        docs: list[str] = []
        seen: set[int] = set()
        for item in passages:
            new = [i for i in held.get(item["passage_id"], []) if i not in seen]
            seen.update(new)
            for index in new:
                quote_ranks[index][stage] = item["rank"]
            if new and first_rank[stage] is None:
                first_rank[stage] = item["rank"]
            docs.extend([f"quote-{i}" for i in new] or [item["passage_id"]])
        # ranx cannot score an empty ranking, so a stage that found nothing
        # ranks one placeholder that is never relevant.
        stage_docs[stage] = {
            doc: float(len(docs) - n) for n, doc in enumerate(docs or [EMPTY])
        }
    rerank = body["stages"]["rerank"]["passages"]
    return Scored(
        question=question,
        quote_ranks=tuple(quote_ranks),
        first_rank=first_rank,
        top_rerank_score=rerank[0]["score"] if rerank else None,
        stage_docs=stage_docs,
    )


def _evaluate(scored: Sequence[Scored]) -> dict[str, dict[str, float]]:
    """Return each metric of each stage over `scored`, computed by ranx."""
    # Imported here: ranx is in the `eval` group, which the app image leaves out.
    ranx = importlib.import_module("ranx")
    qrels = ranx.Qrels(
        {
            s.question.id: {f"quote-{i}": 1 for i in range(len(s.question.evidence))}
            for s in scored
        }
    )
    metrics: dict[str, dict[str, float]] = {}
    for stage in STAGES:
        run = ranx.Run({s.question.id: s.stage_docs[stage] for s in scored})
        values = cast(
            "dict[str, float]",
            ranx.evaluate(qrels, run, list(METRICS), make_comparable=True),
        )
        metrics[stage] = {name: round(float(values[name]), 4) for name in METRICS}
    return metrics


def metrics(scored: Sequence[Scored]) -> dict[str, Any]:
    """Return the metrics per stage, overall and per question type.

    Negative questions have no quotes, so they are left out.
    """
    with_evidence = [s for s in scored if s.question.evidence]
    by_type = {
        kind: [s for s in with_evidence if s.question.type == kind]
        for kind in QUESTION_TYPES
    }
    return {
        "overall": {
            "questions": len(with_evidence),
            "stages": _evaluate(with_evidence) if with_evidence else {},
        },
        "by_type": {
            kind: {"questions": len(group), "stages": _evaluate(group)}
            for kind, group in by_type.items()
            if group
        },
    }
