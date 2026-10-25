# Vendored skills

The skills in this table come from other repositories. The pstack skills are not vendored: `.claude/settings.json` installs the whole pstack plugin from [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude), pinned to tag `v0.9.102`. Its skills carry the `pstack:` prefix. To update it, change the `ref` in `.claude/settings.json`. The local `bstack` skill limits pstack's subagent fan-out.

For each vendored skill, the first commit that added it is a literal copy. Later commits hold the local edits, so `git log -p -- <skill dir>` shows every change.

| Skill | Source | Commit | License |
|---|---|---|---|
| `grill-with-docs` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/engineering/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |
| `domain-modeling` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/engineering/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |
| `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/productivity/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |

## Local edits

- `grill-with-docs`: removed `disable-model-invocation: true`, so `factory-spec` can call it.

## Update a skill

1. Compare the pinned commit with the new upstream commit for the skill's directory.
2. Apply the upstream change. Keep the local edits.
3. Update the commit in this table.
