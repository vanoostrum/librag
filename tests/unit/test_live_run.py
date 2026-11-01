# Copyright (C) 2026 Theo van Oostrum
"""The live run's cost cap and report, over many cost combinations.

A live run cannot reach these cases on demand (an unknown price, a cap just
reached), so they are tested on the usage log directly.
"""

import json

import pytest

from tests.e2e.live import (
    BudgetReachedError,
    ChatRecord,
    EmbeddingRecord,
    UsageLog,
    budget_usd,
)


def _chat(
    model: str = "anthropic/claude-sonnet-5-5",
    cost_usd: float | None = 0.01,
    route: str = "chat",
) -> ChatRecord:
    return ChatRecord(
        model=model,
        route=route,
        question="Why?",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=cost_usd,
        latency_ms=1500.0,
        parts=[{"kind": "book", "text": "Because.", "citations": [1]}],
    )


def test_budget_defaults_to_two_dollars() -> None:
    """Without LIBRAG_LIVE_BUDGET_USD, the cap is $2."""
    assert budget_usd({}) == 2.0  # noqa: PLR2004


def test_budget_reads_the_environment() -> None:
    """LIBRAG_LIVE_BUDGET_USD changes the cap."""
    assert budget_usd({"LIBRAG_LIVE_BUDGET_USD": "0.5"}) == 0.5  # noqa: PLR2004


@pytest.mark.parametrize("raw", ["", "two", "-1", "nan", "inf"])
def test_budget_refuses_a_value_that_is_not_an_amount(raw: str) -> None:
    """A cap that is not a finite amount of at least 0 is an error, with its value."""
    with pytest.raises(ValueError, match="LIBRAG_LIVE_BUDGET_USD"):
        budget_usd({"LIBRAG_LIVE_BUDGET_USD": raw})


def test_known_cost_sums_chats_and_embeddings_and_skips_unknown() -> None:
    """The run's known cost adds each known chat and embedding cost."""
    log = UsageLog()
    log.add_chat(_chat(cost_usd=0.25))
    log.add_chat(_chat(cost_usd=None))
    log.add_chat(_chat(model="openai/gpt-6.1-terra", cost_usd=0.5))
    log.add_embedding(EmbeddingRecord("b1", "Book", tokens=500, cost_usd=0.001))
    log.add_embedding(EmbeddingRecord("b2", "Book", tokens=500, cost_usd=None))
    assert log.known_cost() == pytest.approx(0.751)
    assert log.unknown_costs() == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    ("costs", "cap", "reached"),
    [
        ([], 2.0, False),
        ([1.99], 2.0, False),
        ([1.0, 1.0], 2.0, True),
        ([2.5], 2.0, True),
        ([None, None], 0.01, False),
        ([0.0], 0.0, True),
    ],
)
def test_check_budget_raises_once_the_known_cost_reaches_the_cap(
    costs: list[float | None], cap: float, *, reached: bool
) -> None:
    """The check passes below the cap and raises "budget reached" at or above it."""
    log = UsageLog()
    for cost in costs:
        log.add_chat(_chat(cost_usd=cost))
    if reached:
        with pytest.raises(BudgetReachedError, match=r"^budget reached"):
            log.check_budget(cap)
    else:
        log.check_budget(cap)


def test_report_has_one_row_per_model_and_the_embeddings() -> None:
    """The JSON report sums requests, tokens, cost and latency per model."""
    log = UsageLog()
    log.add_chat(_chat(cost_usd=0.25))
    log.add_chat(_chat(cost_usd=0.25, route="stream"))
    log.add_chat(_chat(model="openai/gpt-6.1-terra", cost_usd=None))
    log.add_embedding(EmbeddingRecord("b1", "Book", tokens=700, cost_usd=0.002))
    report = log.report(budget=2.0)
    assert report["models"] == [
        {
            "model": "anthropic/claude-sonnet-5-5",
            "requests": 2,
            "input_tokens": 2000,
            "output_tokens": 400,
            "cost_usd": 0.5,
            "latency_ms_total": 3000.0,
            "latency_ms_mean": 1500.0,
        },
        {
            "model": "openai/gpt-6.1-terra",
            "requests": 1,
            "input_tokens": 1000,
            "output_tokens": 200,
            "cost_usd": None,
            "latency_ms_total": 1500.0,
            "latency_ms_mean": 1500.0,
        },
    ]
    assert report["embeddings"] == {"books": 1, "tokens": 700, "cost_usd": 0.002}
    assert report["budget_usd"] == 2.0  # noqa: PLR2004
    assert report["known_cost_usd"] == pytest.approx(0.502)
    assert report["warnings"] == [
        (
            "openai/gpt-6.1-terra: 1 request without a known cost; "
            "the cost cap did not count it"
        )
    ]
    # The answers are kept, so a failed live test can be read afterwards.
    assert report["requests"][0]["parts"] == _chat().parts
    json.dumps(report)


def test_table_shows_unknown_cost_and_the_warning() -> None:
    """The printed table says `unknown` for a model without a known cost."""
    log = UsageLog()
    log.add_chat(_chat(cost_usd=0.0123))
    log.add_chat(_chat(model="openai/gpt-6.1-terra", cost_usd=None))
    log.add_embedding(EmbeddingRecord("b1", "Book", tokens=700, cost_usd=None))
    table = log.table(budget=2.0)
    lines = table.splitlines()
    claude = next(line for line in lines if "claude-sonnet-5-5" in line)
    terra = next(line for line in lines if "gpt-6.1-terra" in line)
    embeddings = next(line for line in lines if line.startswith("embeddings"))
    assert "$0.0123" in claude
    assert "1,000" in claude
    assert "unknown" in terra
    assert "700" in embeddings
    assert "unknown" in embeddings
    assert "known cost $0.0123 of the $2.00 cap" in table
    assert (
        "warning: openai/gpt-6.1-terra: 1 request without a known cost; "
        "the cost cap did not count it"
    ) in table
    assert (
        "warning: embeddings: 1 book without a known cost; "
        "the cost cap did not count it"
    ) in table


def test_table_of_an_empty_run_says_so() -> None:
    """A live run with no chat requests prints a table with no model rows."""
    table = UsageLog().table(budget=2.0)
    assert "no chat requests" in table
    assert "known cost $0.0000 of the $2.00 cap" in table
