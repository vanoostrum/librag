# Vendored skills

These skills come from other repositories. The first commit that added them is a literal copy. Later commits hold the local edits, so `git log -p -- <skill dir>` shows every change.

| Skill | Source | Commit | License |
|---|---|---|---|
| `create-verification-skill` | [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude), `plugins/pstack/skills/` | `046341e3aaf2405083973a37f860d0d2ea98e18a` | MIT, Copyright (c) 2026 Lauren Tan |
| `maintain-verification-skill` | [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude), `plugins/pstack/skills/` | `046341e3aaf2405083973a37f860d0d2ea98e18a` | MIT, Copyright (c) 2026 Lauren Tan |
| `grill-with-docs` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/engineering/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |
| `domain-modeling` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/engineering/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |
| `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/productivity/` | `49dd158d1076134a641b33efb035946536778336` | MIT, Copyright (c) 2026 Matt Pocock |

## Local edits

- `create-verification-skill`, `maintain-verification-skill`: removed the two lines for Codex and GitHub Copilot. They link to `poteto-mode`, which is not vendored.
- `grill-with-docs`: removed `disable-model-invocation: true`, so `factory-spec` can call it.

## Update a skill

1. Compare the pinned commit with the new upstream commit for the skill's directory.
2. Apply the upstream change. Keep the local edits.
3. Update the commit in this table.
