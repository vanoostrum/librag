# Copyright (C) 2026 Theo van Oostrum
"""The answer evaluation: ask the evaluation set through chat and save the answers.

Each answer is saved with its cited passages, an evidence check, its usage,
and optional Ragas scores, so it can be graded on the grading page later.
"""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from librag.evaluation.evalset import EvalSet, Question, contains
from librag.evaluation.judge import Judge
from librag.evaluation.stack import EvalError, Stack
from librag.evaluation.usage import BudgetReachedError, ChatRecord, UsageLog

CITATION_FIELDS = ("n", "passage_id", "title", "author", "chapter", "section", "text")


def answer_hash(parts: Sequence[Mapping[str, Any]], citations: Sequence[Any]) -> str:
    """Return a short hash of an answer's parts and cited passages.

    Two answers with the same hash read the same and cite the same text, so a
    grade of one holds for the other.
    """
    data = {
        "parts": [
            {key: part[key] for key in ("kind", "text", "citations")} for part in parts
        ],
        "citations": [
            {key: citation[key] for key in ("n", "passage_id", "text")}
            for citation in citations
        ],
    }
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def evidence_check(
    question: Question,
    parts: Sequence[Mapping[str, Any]],
    citations: Sequence[Mapping[str, Any]],
    book_ids: Mapping[str, str],
) -> dict[str, Any]:
    """Return which evidence quotes the cited passages contain, and if it passed.

    A question with evidence passes when every quote is in a passage the answer
    cites. A negative question passes when the answer makes no book claims.
    """
    if not question.evidence:
        claims = sum(1 for part in parts if part["kind"] == "book")
        return {"passed": claims == 0, "book_claims": claims, "quotes": []}
    quotes = [
        {
            "book": evidence.book,
            "quote": evidence.quote,
            "cited_in": [
                citation["n"]
                for citation in citations
                if citation["book_id"] == book_ids[evidence.book]
                and contains(citation["text"], evidence.quote)
            ],
        }
        for evidence in question.evidence
    ]
    return {"passed": all(quote["cited_in"] for quote in quotes), "quotes": quotes}


def _context_texts(body: Mapping[str, Any]) -> list[str]:
    """Return the texts of the passages that the answer's prompt held, in order."""
    retrieval = body["retrieval"]
    texts = {c["passage_id"]: c["text"] for c in retrieval["candidates"]}
    return [texts[passage_id] for passage_id in retrieval["context"]["passage_ids"]]


def _answer_text(parts: Sequence[Mapping[str, Any]]) -> str:
    return "\n\n".join(str(part["text"]) for part in parts)


@dataclass
class AnswerRun:
    """One run: every question on every model, with the cap and the optional judge."""

    stack: Stack
    evalset: EvalSet
    books: Mapping[str, Mapping[str, Any]]
    models: Sequence[str]
    budget: float
    judge: Judge | None = None
    log: Callable[[str], None] = print

    def __post_init__(self) -> None:
        """Start with an empty usage log and no answers."""
        self.usage = UsageLog()
        self.answers: list[dict[str, Any]] = []
        self.book_ids = {key: entry["id"] for key, entry in self.books.items()}
        self.book_keys = {book_id: key for key, book_id in self.book_ids.items()}

    def run(self) -> str | None:
        """Ask every question on every model; return why the run stopped early.

        The run stops when the cap is reached or a chat request fails. The
        answers so far stay in `answers`.
        """
        try:
            for question in self.evalset.questions:
                for model in self.models:
                    self.answers.append(self._ask(question, model))
        except BudgetReachedError as error:
            return str(error)
        except EvalError as error:
            return str(error)
        return None

    def _chat_body(self, question: Question, model: str) -> dict[str, Any]:
        keys = question.books or list(self.book_ids)
        return {
            "question": question.question,
            "model": model,
            # Only the evaluation books, so the rest of the library never shows up.
            "book_ids": [self.book_ids[key] for key in keys],
            "authors": list(question.authors),
        }

    def _ask(self, question: Question, model: str) -> dict[str, Any]:
        self.usage.check_budget(self.budget)
        self.log(f"{question.id} on {model}")
        body = self.stack.chat(self._chat_body(question, model))
        usage = body["usage"]
        self.usage.add_chat(
            ChatRecord(
                model=model,
                route="chat",
                question=question.question,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=usage["cost_usd"],
                latency_ms=usage["latency_ms"],
                parts=body["parts"],
            )
        )
        citations = [
            {
                "book": self.book_keys.get(citation["book_id"]),
                "book_id": citation["book_id"],
                **{key: citation[key] for key in CITATION_FIELDS},
            }
            for citation in body["citations"]
        ]
        answer = {
            "question_id": question.id,
            "type": question.type,
            "question": question.question,
            "model": model,
            "answer_hash": answer_hash(body["parts"], body["citations"]),
            "parts": body["parts"],
            "citations": citations,
            "evidence": evidence_check(
                question, body["parts"], body["citations"], self.book_ids
            ),
            "usage": usage,
            "ragas": None,
        }
        if self.judge is not None:
            answer["ragas"] = self._judge(question, body)
        return answer

    def _judge(self, question: Question, body: Mapping[str, Any]) -> dict[str, Any]:
        assert self.judge is not None  # noqa: S101 - only called with a judge
        self.usage.check_budget(self.budget)
        judgement = self.judge.judge(
            question.question, _answer_text(body["parts"]), _context_texts(body)
        )
        self.usage.add_chat(
            ChatRecord(
                model=f"{self.judge.model} (Ragas judge)",
                route="ragas",
                question=question.question,
                input_tokens=judgement.input_tokens,
                output_tokens=judgement.output_tokens,
                cost_usd=judgement.cost_usd,
                latency_ms=judgement.latency_ms,
                parts=[],
            )
        )
        return {
            "faithfulness": judgement.faithfulness,
            "answer_relevancy": judgement.answer_relevancy,
            "judge_model": self.judge.model,
            "cost_usd": judgement.cost_usd,
        }
