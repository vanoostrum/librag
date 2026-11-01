# Copyright (C) 2026 Theo van Oostrum
"""`scripts/e2e-live` checks its keys, runs the suite live, and always tears down.

The script runs with stand-ins for `docker` and `uv` on PATH, which log their
arguments, so the test needs no Docker, no API keys and no network.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "e2e-live"
KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
COMPOSE = "docker compose -p librag-live -f compose.yaml"
STAND_IN = """#!/usr/bin/env bash
name="$(basename "$0")"
echo "$name $* | live=${LIBRAG_E2E_LIVE:-} url=${LIBRAG_E2E_URL:-}" >> "$CALLS"
case "$name $*" in
  "docker compose"*" up "*) exit "${UP_EXIT:-0}" ;;
  "uv run pytest"*) exit "${PYTEST_EXIT:-0}" ;;
esac
"""


def _run(
    tmp_path: Path, env: dict[str, str], *args: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the script with stand-ins; return the result and the logged calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("docker", "uv"):
        stand_in = bin_dir / name
        stand_in.write_text(STAND_IN, encoding="utf-8")
        stand_in.chmod(0o755)
    calls = tmp_path / "calls.log"
    base = {k: v for k, v in os.environ.items() if k not in KEYS}
    base.pop("LIBRAG_LIVE_BUDGET_USD", None)
    full_env = {
        **base,
        "PATH": f"{bin_dir}{os.pathsep}{base['PATH']}",
        "CALLS": str(calls),
        **env,
    }
    result = subprocess.run(  # noqa: S603 - the script is in the repo
        [str(SCRIPT), *args],
        env=full_env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    logged = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, logged


KEYS_SET = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "sk-ant-test"}


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({}, "OPENAI_API_KEY ANTHROPIC_API_KEY"),
        ({"OPENAI_API_KEY": "sk-test"}, "ANTHROPIC_API_KEY"),
        ({"ANTHROPIC_API_KEY": "sk-ant-test"}, "OPENAI_API_KEY"),
        ({"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "sk"}, "OPENAI_API_KEY"),
    ],
)
def test_refuses_to_start_without_both_keys(
    tmp_path: Path, env: dict[str, str], missing: str
) -> None:
    """A missing key stops the script before it starts anything, and names the key."""
    result, calls = _run(tmp_path, env)
    assert result.returncode == 2  # noqa: PLR2004
    assert f"set {missing} in your shell" in result.stderr
    assert calls == []


@pytest.mark.parametrize("budget", ["", "two", "-1", "1e3"])
def test_refuses_a_cap_that_is_not_an_amount(tmp_path: Path, budget: str) -> None:
    """A cap that is not an amount in dollars stops the script before it starts."""
    result, calls = _run(tmp_path, {**KEYS_SET, "LIBRAG_LIVE_BUDGET_USD": budget})
    assert result.returncode == 2  # noqa: PLR2004
    assert "LIBRAG_LIVE_BUDGET_USD must be an amount in dollars" in result.stderr
    assert calls == []


def test_runs_the_suite_live_against_its_own_stack(tmp_path: Path) -> None:
    """With both keys it starts librag-live, runs tests/e2e live, then tears down."""
    result, calls = _run(tmp_path, KEYS_SET, "-k", "cross_book")
    assert result.returncode == 0, result.stderr
    assert calls == [
        f"{COMPOSE} up -d --build --wait --wait-timeout 600 | live= url=",
        (
            "uv run pytest tests/e2e --no-cov -k cross_book"
            " | live=1 url=http://localhost:8100"
        ),
        f"{COMPOSE} down -v --remove-orphans | live= url=",
    ]
    assert "cost cap of $2" in result.stdout


def test_tears_down_when_a_test_fails(tmp_path: Path) -> None:
    """A failing test fails the script, and the stack is still torn down."""
    result, calls = _run(tmp_path, {**KEYS_SET, "PYTEST_EXIT": "1"})
    assert result.returncode == 1
    assert calls[-1].startswith(f"{COMPOSE} down -v")


def test_tears_down_when_the_stack_does_not_start(tmp_path: Path) -> None:
    """A stack that fails to start runs no tests, and is still torn down."""
    result, calls = _run(tmp_path, {**KEYS_SET, "UP_EXIT": "1"})
    assert result.returncode == 1
    assert [call.split(" |")[0] for call in calls] == [
        f"{COMPOSE} up -d --build --wait --wait-timeout 600",
        f"{COMPOSE} down -v --remove-orphans",
    ]


def test_port_and_cap_come_from_the_environment(tmp_path: Path) -> None:
    """LIBRAG_LIVE_PORT moves the stack, and the script shows the cap it runs with."""
    env = {**KEYS_SET, "LIBRAG_LIVE_PORT": "9100", "LIBRAG_LIVE_BUDGET_USD": "0.5"}
    result, calls = _run(tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert "url=http://localhost:9100" in calls[1]
    assert "cost cap of $0.5" in result.stdout
