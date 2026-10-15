# CLAUDE.md

**LibRag** is a Python FastAPI web application.

## Project

| Path | What |
|---|---|
| `src/librag/` | Application code. `main.py` holds the FastAPI app. |
| `tests/unit/` | Tests that call functions directly. |
| `tests/integration/` | Tests that go through HTTP with `TestClient`. |
| `.github/workflows/ci.yml` | CI: ruff, ty, pytest. |

- Python 3.12, managed with **uv**. Add dependencies with `uv add`, never `pip`.
- Lint with **ruff**, type-check with **ty**, test with **pytest**. All must pass.
- Write tests first.
- How to run and verify: the `project-verify` skill.

## Factory

This repo is worked on by a software factory: Claude Code agents take a Linear ticket through **spec → build → test → review → merge**. A human approves at two gates: the spec, and the merge. The `factory-*` skills hold the steps; they are generic and read the values below.

### Factory config

| Key | Value |
|---|---|
| Linear team | `LIBRAG` |
| GitHub repo | `vanoostrum/librag` |
| Base branch | `main` |
| Bot user | `cbchef` |
| Bot email | `343190287+cbchef@users.noreply.github.com` |
| Bot token env var | `FACTORY_GITHUB_TOKEN` |
| Required CI check | `checks` |
| Verify skill | `project-verify` |

### Flow

| Step | Skill | Linear state |
|---|---|---|
| Spec | `factory-spec` | In Progress |
| 🚦 Gate 1: approve spec | — | In Progress |
| Build + test | `factory-build` | In Progress |
| Review | `factory-review` | In Review |
| 🚦 Gate 2: approve merge | — | In Review |
| Merge | `factory-merge` | Done |

When asked to "work on" a ticket or a feature, run the steps in order from wherever the ticket is. Stop at each gate.

### Rules for every step

- **Linear is the source of truth.** Read the ticket's current state and comments before acting. Do not rely on memory of earlier sessions.
- **Factory comments.** Every comment the factory writes in Linear starts with `🤖`. Comments without it are from the human. Each step adds one comment when it ends: `🤖 <step>: <success|failed|escalated> — <one line>`.
- **Gates.** At a gate, post `🤖 Gate: spec` or `🤖 Gate: merge` with a short summary and the question, then stop and ask the human in chat too. The gate is approved when either:
  - the human says "approve" in this chat. Then post `🤖 Approved: <gate> (in chat)` on the ticket, or
  - a human comment on the ticket after the latest gate comment says "approve".

  Any other human reply is feedback: go back to the step before the gate and use it.
- **Retries.** At most 3 failed attempts per step. Then move the ticket to **Needs human**, comment what was tried and what blocks, and tell the human.
- **GitHub identity.** All git and GitHub actions run as the bot user, never as the human:
  - `git config user.name <bot user>` and `git config user.email <bot email>` before committing.
  - Use the token in the bot token env var for `git push` and `gh` (`GH_TOKEN=$FACTORY_GITHUB_TOKEN`).
  - If the env var is missing, stop and tell the human. Do not fall back to another identity.
  - Use `gh api` with REST endpoints only. The cloud sandbox blocks GitHub's GraphQL API, so `gh pr ...` commands fail there.
- **Git.** Branch `<team lowercase>-<num>/<slug>`, e.g. `librag-12/version-endpoint`. PR title `[<TEAM>-<num>] <title>`. Every commit ends with the trailer `Factory-Issue: <TEAM>-<num>`. Never push to the base branch. Never commit secrets.
