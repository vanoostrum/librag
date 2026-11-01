# Copyright (C) 2026 Theo van Oostrum
"""A 👍 on the gate message in chat approves a factory gate."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".claude" / "skills"
GATE_STEPS = ["factory-plan", "factory-spec", "factory-review"]


def gates_rule() -> str:
    """Return the Gates rule from `CLAUDE.md`."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    return text.split("- **Gates.**", 1)[1].split("\n- **", 1)[0]


def test_gates_rule_accepts_a_thumbs_up() -> None:
    """The Gates rule counts a 👍 reaction in chat as approval."""
    rule = gates_rule()
    assert "👍" in rule
    assert "🤖 Approved: <gate> (👍 in chat)" in rule


@pytest.mark.parametrize("skill", GATE_STEPS)
def test_gate_step_offers_a_thumbs_up(skill: str) -> None:
    """Each step that stops at a gate tells the human that 👍 approves."""
    text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    assert "👍" in text
