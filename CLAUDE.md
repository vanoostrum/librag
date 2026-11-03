# CLAUDE.md

**LibRag** is a Python FastAPI web application.

## Project

| Path | What |
|---|---|
| `src/librag/` | Application code. `main.py` holds the FastAPI app. |
| `tests/integration/` | Tests that go through HTTP with `TestClient`. The default place for tests. |
| `tests/unit/` | Tests that call functions directly. Only where the test seam rule allows them. |
| `tests/repo/` | Tests that check repository configuration, such as `compose.yaml`. |
| `design/` | The design gallery: the visual spec of each screen. `design/README.md` has its state; the rules are in the sous plugin. |
| `.github/workflows/ci.yml` | CI: ruff, ty, pytest with a coverage report. |

- Python 3.12, managed with **uv**. Add dependencies with `uv add`, never `pip`.
- Lint with **ruff**, type-check with **ty**, test with **pytest**. All must pass.
- Write tests first.
- **Test seams.** Test a feature at the highest seam: its HTTP route, with `TestClient`. Add a unit test only when the route test cannot cover a case well: many input combinations, a case that no request can reach, or a failure that is hard to locate from the route. Do not repeat in a unit test what a route test already checks. Test behavior that a client sees, not internals.
- pytest reports line and branch coverage on every run. There is no minimum. A branch that no test reaches is a sign that a case needs a test.
- How to run and verify: the `project-verify` skill.
- **pstack.** The sous marketplace installs pstack next to sous. Load the `sous:bstack` skill before any `pstack:` skill; a hook in the sous plugin blocks pstack skills until bstack is loaded. Where bstack differs from pstack, including pstack's session-start instruction to use `pstack:poteto-mode`, bstack wins.
- **Unknown skills.** If a skill is unknown, read `.claude/skills/<name>/SKILL.md` and follow it.

## Sous

This repo is a kitchen of [sous](https://github.com/vanoostrum/sous), a Claude Code plugin that takes a Linear ticket through **spec → build → test → review → merge**, and stops at the pass for chef's approval. The `sous:*` skills hold the steps, and `sous:rules` holds the rules for every step. They read the values below.

@.claude/kitchen.md
