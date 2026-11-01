# Copyright (C) 2026 Theo van Oostrum
"""The e2e suite's switches: fake or live, the chat models, and the live report.

`LIBRAG_E2E_LIVE=1` (set by `scripts/e2e-live`) runs the suite against the real
AI providers. Tests marked `fake_only` depend on what the fakes answer and are
skipped then; tests marked `live_only` run only then. At the end of a live run
the suite prints its usage per model and writes it to `e2e-reports/`.
"""

import functools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.e2e import stack
from tests.e2e.live import LIVE

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "e2e-reports"


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers of the fake and the live run."""
    config.addinivalue_line(
        "markers", "fake_only: depends on the fakes; skipped in a live run"
    )
    config.addinivalue_line("markers", "live_only: runs only in a live run")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip the tests that do not apply to this run."""
    for item in items:
        if LIVE and item.get_closest_marker("fake_only"):
            item.add_marker(pytest.mark.skip(reason="depends on the fakes"))
        if not LIVE and item.get_closest_marker("live_only"):
            item.add_marker(pytest.mark.skip(reason="needs a live run"))


@functools.cache
def _models() -> tuple[str, ...]:
    return tuple(stack.chat_models())


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Run each test that takes `model` once per model of the running stack."""
    if "model" in metafunc.fixturenames:
        models = _models()
        metafunc.parametrize("model", models, ids=models)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """At the end of a live run, print the usage table and write the JSON report."""
    if not LIVE:
        return
    terminalreporter.write_sep("=", "live run usage")
    terminalreporter.write_line(stack.USAGE.table(stack.BUDGET_USD))
    REPORTS.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    path = REPORTS / f"{now:%Y%m%d-%H%M%S}.json"
    report = {
        "created_at": now.isoformat(),
        "url": stack.BASE_URL,
        **stack.USAGE.report(stack.BUDGET_USD),
    }
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    terminalreporter.write_line(f"report: {path.relative_to(ROOT)}")
