# Copyright (C) 2026 Theo van Oostrum
"""Each ticket's spec runs in a fresh session that gets a brief of its blockers."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".claude" / "skills"


def skill(name: str) -> str:
    """Return the text of a skill's `SKILL.md`."""
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def lane_row(lane: str) -> str:
    """Return the row of the lanes table in `factory-next` for `lane`."""
    rows = [
        line
        for line in skill("factory-next").splitlines()
        if line.startswith(f"| {lane} |")
    ]
    assert len(rows) == 1
    return rows[0]


def test_spec_lane_runs_in_a_new_session() -> None:
    """The spec lane starts `factory-spec` in a new session, like the build lane."""
    row = lane_row("Spec")
    assert "new session" in row
    assert "this session" not in row


def test_spec_lane_passes_a_blocker_brief() -> None:
    """The spec lane's prompt carries a brief of the tickets that block the ticket."""
    step = skill("factory-next").split("**Spec lane.**", 1)[1].split("\n5. ", 1)[0]
    assert "Brief:" in step
    assert "blocks" in step


def test_spec_reads_the_brief() -> None:
    """`factory-spec` takes the brief of the blocking tickets as input."""
    text = skill("factory-spec")
    inputs = text.split("## Input", 1)[1].split("\n## ", 1)[0]
    assert "brief" in inputs
