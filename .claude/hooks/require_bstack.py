# Copyright (C) 2026 Theo van Oostrum
"""PreToolUse hook: block pstack skills until bstack is loaded in the session.

Claude Code runs this before every Skill tool call and passes the call as JSON
on stdin. A `pstack:` skill is denied unless the transcript shows that `bstack`
was loaded after the last compaction, by the Skill tool or by `/bstack`.
"""

import json
import sys
from pathlib import Path
from typing import Any

BUDGET_SKILL = "bstack"
GATED_PREFIX = "pstack:"
SLASH_COMMAND = f"<command-name>/{BUDGET_SKILL}</command-name>"
REASON = (
    f"Load the {BUDGET_SKILL} skill with the Skill tool first, follow it, "
    "then retry this pstack skill."
)


def loads_budget_skill(entry: dict[str, Any]) -> bool:
    """Return whether a transcript entry loads the budget skill."""
    content = (entry.get("message") or {}).get("content")
    if entry.get("type") == "user":
        if isinstance(content, str):
            return SLASH_COMMAND in content
        texts = [
            block.get("text") or ""
            for block in content or []
            if block.get("type") == "text"
        ]
        return any(SLASH_COMMAND in text for text in texts)
    if entry.get("type") == "assistant" and isinstance(content, list):
        return any(
            block.get("type") == "tool_use"
            and block.get("name") == "Skill"
            and (block.get("input") or {}).get("skill") == BUDGET_SKILL
            for block in content
        )
    return False


def budget_skill_loaded(transcript: Path) -> bool:
    """Return whether the budget skill was loaded since the last compaction."""
    loaded = False
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("subtype") == "compact_boundary":
            loaded = False
        elif loads_budget_skill(entry):
            loaded = True
    return loaded


def main() -> None:
    """Deny a pstack Skill call when the budget skill is not loaded."""
    call = json.load(sys.stdin)
    skill = (call.get("tool_input") or {}).get("skill") or ""
    if not skill.startswith(GATED_PREFIX):
        return
    transcript = Path(call.get("transcript_path") or "")
    if transcript.is_file() and budget_skill_loaded(transcript):
        return
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        },
    }
    sys.stdout.write(json.dumps(decision) + "\n")


if __name__ == "__main__":
    main()
