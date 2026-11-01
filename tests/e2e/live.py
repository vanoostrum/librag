# Copyright (C) 2026 Theo van Oostrum
"""The live run: its switch, its cost cap, and its usage report.

A live run is the e2e suite against the real AI providers, started by hand
with `scripts/e2e-live`. The suite logs the usage of each chat request and
each indexed book, checks the cap before each chat request, and reports the
tokens and cost per model at the end.
"""

import math
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

LIVE = os.environ.get("LIBRAG_E2E_LIVE") == "1"
BUDGET_VARIABLE = "LIBRAG_LIVE_BUDGET_USD"
DEFAULT_BUDGET_USD = 2.0


def budget_usd(environ: Mapping[str, str]) -> float:
    """Return the cost cap in `LIBRAG_LIVE_BUDGET_USD`, or $2 without it."""
    raw = environ.get(BUDGET_VARIABLE)
    if raw is None:
        return DEFAULT_BUDGET_USD
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not math.isfinite(value) or value < 0:
        msg = (
            f"{BUDGET_VARIABLE} must be an amount in dollars of at least 0, not {raw!r}"
        )
        raise ValueError(msg)
    return value


class BudgetReachedError(Exception):
    """The run's known cost reached the cap, so no more chat requests are sent."""


@dataclass(frozen=True)
class ChatRecord:
    """One answered chat request: its model, route, usage and answer."""

    model: str
    route: str
    question: str
    input_tokens: int
    output_tokens: int
    # None when LiteLLM does not know the model's price.
    cost_usd: float | None
    latency_ms: float
    parts: list[dict[str, Any]]


@dataclass(frozen=True)
class EmbeddingRecord:
    """What embedding one indexed book cost."""

    book_id: str
    title: str
    tokens: int
    cost_usd: float | None


def _sum_cost(costs: list[float | None]) -> float | None:
    """Return the sum of `costs`, or None when any of them is unknown."""
    if any(cost is None for cost in costs):
        return None
    return sum(cost for cost in costs if cost is not None)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _money(cost: float | None) -> str:
    return "unknown" if cost is None else f"${cost:.4f}"


@dataclass
class UsageLog:
    """The usage of a run, in the order the suite logged it."""

    chats: list[ChatRecord] = field(default_factory=list)
    embeddings: list[EmbeddingRecord] = field(default_factory=list)

    def add_chat(self, record: ChatRecord) -> None:
        """Log one answered chat request."""
        self.chats.append(record)

    def add_embedding(self, record: EmbeddingRecord) -> None:
        """Log what embedding one indexed book cost."""
        self.embeddings.append(record)

    def known_cost(self) -> float:
        """Return the sum of every known chat and embedding cost."""
        costs = [record.cost_usd for record in (*self.chats, *self.embeddings)]
        return sum(cost for cost in costs if cost is not None)

    def unknown_costs(self) -> int:
        """Return how many logged records have no known cost."""
        records = (*self.chats, *self.embeddings)
        return sum(1 for record in records if record.cost_usd is None)

    def check_budget(self, budget: float) -> None:
        """Raise `BudgetReachedError` once the known cost reaches `budget`."""
        spent = self.known_cost()
        if spent >= budget:
            msg = (
                f"budget reached: the run's known cost is ${spent:.4f}, and the cap "
                f"is ${budget:.2f} ({BUDGET_VARIABLE}). No request was sent."
            )
            raise BudgetReachedError(msg)

    def _models(self) -> list[dict[str, Any]]:
        rows = []
        for model in dict.fromkeys(record.model for record in self.chats):
            records = [record for record in self.chats if record.model == model]
            latency = sum(record.latency_ms for record in records)
            rows.append(
                {
                    "model": model,
                    "requests": len(records),
                    "input_tokens": sum(record.input_tokens for record in records),
                    "output_tokens": sum(record.output_tokens for record in records),
                    "cost_usd": _sum_cost([record.cost_usd for record in records]),
                    "latency_ms_total": round(latency, 3),
                    "latency_ms_mean": round(latency / len(records), 3),
                }
            )
        return rows

    def _warnings(self) -> list[str]:
        warnings = []
        for model in dict.fromkeys(record.model for record in self.chats):
            unknown = sum(
                1
                for record in self.chats
                if record.model == model and record.cost_usd is None
            )
            if unknown:
                warnings.append(
                    f"{model}: {_plural(unknown, 'request')} without a known cost; "
                    "the cost cap did not count it"
                )
        unknown = sum(1 for record in self.embeddings if record.cost_usd is None)
        if unknown:
            warnings.append(
                f"embeddings: {_plural(unknown, 'book')} without a known cost; "
                "the cost cap did not count it"
            )
        return warnings

    def report(self, budget: float) -> dict[str, Any]:
        """Return the run's usage per model and for the embeddings, as JSON data."""
        return {
            "budget_usd": budget,
            "known_cost_usd": self.known_cost(),
            "models": self._models(),
            "embeddings": {
                "books": len(self.embeddings),
                "tokens": sum(record.tokens for record in self.embeddings),
                "cost_usd": _sum_cost([record.cost_usd for record in self.embeddings]),
            },
            "warnings": self._warnings(),
            "requests": [asdict(record) for record in self.chats],
            "books": [asdict(record) for record in self.embeddings],
        }

    def table(self, budget: float) -> str:
        """Return the report as a table to print at the end of the run."""
        report = self.report(budget)
        header = ("model", "requests", "input", "output", "cost", "mean latency")
        rows = [
            (
                row["model"],
                f"{row['requests']:,}",
                f"{row['input_tokens']:,}",
                f"{row['output_tokens']:,}",
                _money(row["cost_usd"]),
                f"{row['latency_ms_mean'] / 1000:.1f} s",
            )
            for row in report["models"]
        ]
        embeddings = report["embeddings"]
        rows.append(
            (
                "embeddings",
                f"{embeddings['books']:,} books",
                f"{embeddings['tokens']:,}",
                "",
                _money(embeddings["cost_usd"]),
                "",
            )
        )
        widths = [max(len(row[i]) for row in (header, *rows)) for i in range(6)]

        def line(cells: tuple[str, ...]) -> str:
            first = cells[0].ljust(widths[0])
            rest = (
                cell.rjust(width)
                for cell, width in zip(cells[1:], widths[1:], strict=True)
            )
            return "  ".join((first, *rest)).rstrip()

        lines = [line(header)]
        if not report["models"]:
            lines.append("(no chat requests)")
        lines.extend(line(row) for row in rows)
        lines.append(
            f"known cost {_money(report['known_cost_usd'])} of the ${budget:.2f} cap"
        )
        lines.extend(f"warning: {warning}" for warning in report["warnings"])
        return "\n".join(lines)
