# Copyright (C) 2026 Theo van Oostrum
"""LibRag is a project of the craft plugin."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = (
    "Linear team",
    "GitHub repo",
    "Base branch",
    "Required CI checks",
    "Verify skill",
    "App driver skill",
)


def test_settings_leave_plugins_to_the_account() -> None:
    """The repo settings neither add the craft marketplace nor enable plugins."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))
    assert "extraKnownMarketplaces" not in settings
    assert "enabledPlugins" not in settings


def test_craft_config_has_every_key() -> None:
    """`.claude/craft.md` holds each value that the craft steps read."""
    text = (ROOT / ".claude" / "craft.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| ([^|]+?) \| ([^|]+?) \|$", text, re.MULTILINE))
    for key in KEYS:
        assert rows.get(key, "").startswith("`"), key


def test_project_skills_resolve_in_project_threads() -> None:
    """`CLAUDE.md` imports the config and loads project skills by path."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "\n@.claude/craft.md\n" in text
    assert "If a skill is unknown, read `.claude/skills/<name>/SKILL.md`" in text
    for skill in ("project-verify", "verify"):
        assert (ROOT / ".claude" / "skills" / skill / "SKILL.md").is_file()
