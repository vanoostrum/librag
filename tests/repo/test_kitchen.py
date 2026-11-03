# Copyright (C) 2026 Theo van Oostrum
"""LibRag is a kitchen of the sous plugin."""

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


def test_settings_install_sous_at_a_tag() -> None:
    """Terminal and web sessions get sous and pstack from the sous marketplace."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))
    source = settings["extraKnownMarketplaces"]["sous"]["source"]
    assert source["repo"] == "vanoostrum/sous"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", source["ref"])
    assert settings["enabledPlugins"] == {"sous@sous": True, "pstack@sous": True}


def test_kitchen_config_has_every_key() -> None:
    """`.claude/kitchen.md` holds each value that the sous steps read."""
    text = (ROOT / ".claude" / "kitchen.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| ([^|]+?) \| ([^|]+?) \|$", text, re.MULTILINE))
    for key in KEYS:
        assert rows.get(key, "").startswith("`"), key


def test_kitchen_skills_resolve_in_project_threads() -> None:
    """`CLAUDE.md` imports the config and loads kitchen skills by path."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "\n@.claude/kitchen.md\n" in text
    assert "If a skill is unknown, read `.claude/skills/<name>/SKILL.md`" in text
    for skill in ("project-verify", "verify"):
        assert (ROOT / ".claude" / "skills" / skill / "SKILL.md").is_file()
