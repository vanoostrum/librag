# CLAUDE.md

**LibRag** is a Python FastAPI web application.

## Project

| Path | What |
|---|---|
| `src/librag/` | Application code. `main.py` holds the FastAPI app. |
| `tests/integration/` | Tests that go through HTTP with `TestClient`. The default place for tests. |
| `tests/unit/` | Tests that call functions directly. Only where the test seam rule allows them. |
| `tests/repo/` | Tests that check repository configuration, such as `.claude/models.md`. |
| `design/` | The design gallery: the visual spec of each screen. `design/README.md` has its layout, rules, and rollout stages. |
| `.github/workflows/ci.yml` | CI: ruff, ty, pytest with a coverage report. |

- Python 3.12, managed with **uv**. Add dependencies with `uv add`, never `pip`.
- Lint with **ruff**, type-check with **ty**, test with **pytest**. All must pass.
- Write tests first.
- **Test seams.** Test a feature at the highest seam: its HTTP route, with `TestClient`. Add a unit test only when the route test cannot cover a case well: many input combinations, a case that no request can reach, or a failure that is hard to locate from the route. Do not repeat in a unit test what a route test already checks. Test behavior that a client sees, not internals.
- pytest reports line and branch coverage on every run. There is no minimum. A branch that no test reaches is a sign that a case needs a test.
- How to run and verify: the `project-verify` skill.
- **pstack.** `.claude/settings.json` installs the pstack plugin. Load the `bstack` skill before any `pstack:` skill; a hook in `.claude/hooks/` blocks pstack skills until bstack is loaded. Where bstack differs from pstack, including pstack's session-start instruction to use `pstack:poteto-mode`, bstack wins.

## Factory

This repo is worked on by a software factory: Claude Code agents take a Linear ticket through **spec → build → test → review → merge**. A human approves at two gates: the spec, and the merge. The `factory-*` skills hold the steps; they are generic and read the values below.

### Factory config

| Key | Value |
|---|---|
| Linear team | `LIBRAG` |
| GitHub repo | `vanoostrum/librag` |
| Base branch | `main` |
| Required CI check | `checks` |
| Verify skill | `project-verify` |
| App driver skill | `verify` |
| Models | `.claude/models.md` |
| Design gallery | `design/` |
| UI label | `ui` |

### Flow

| Step | Skill | Linear state |
|---|---|---|
| Step | Skill | Lane | Linear state |
|---|---|---|---|
| Plan, once per project or increment, with a fresh-agent review | `factory-plan` | — | Plan ticket: Specifying |
| 🚦 Gate 0: approve plan | — | — | Plan ticket: Specifying |
| Pick the next ticket for each lane | `factory-next` | — | Todo, or Ready to build |
| Spec, with `grill-with-docs` | `factory-spec` | spec | Specifying |
| Design, for tickets with the `ui` label | `factory-design` | spec | Specifying |
| 🚦 Gate 1: approve spec, with the replan check | — | spec | Specifying, then Ready to build |
| Build + test | `factory-build` | build | Building |
| Review | `factory-review` | build | In Review |
| 🚦 Gate 2: approve merge | — | build | In Review |
| Merge, with the replan check | `factory-merge` | build | Done |

The factory works in two lanes, in parallel. The spec lane needs the human and runs one or two tickets ahead. The build lane runs on its own, up to the merge gate. `factory-next` picks the ticket for each lane and holds the lane rules, the replan check, and the milestone checkpoint.

When asked to "work on" a ticket or a feature, run the steps in order from wherever the ticket is. Stop at each gate. Start at `factory-plan` for a project spec, or for new work that spans more than one or two tickets or adds a new user flow. Otherwise start at `factory-spec`. `factory-spec` runs `factory-design` itself. When asked to "work on the plan" or to "pick up the next ticket", run `factory-next`.

### Rules for every step

- **Linear is the source of truth.** Read the ticket's current state and comments before acting. Do not rely on memory of earlier sessions.
- **Factory comments.** Every comment the factory writes in Linear starts with `🤖`. Comments without it are from the human. Each step adds one comment when it ends: `🤖 <step>: <success|failed|escalated> — <one line>`.
- **Dependencies.** A ticket with a Linear "blocked by" relation is not built until each ticket that blocks it is Done. `factory-next` and `factory-build` check this.
- **Steering.** `factory-plan` and `factory-spec` take optional arguments after their input, as `key=value`. Scope is not an argument: `factory-plan` decides from the repo whether the work is a new project or an increment.

  | Argument | Default | Effect |
  |---|---|---|
  | `design-variants=<n>` | `1` | `factory-design` draws `n` distinct prototypes of each new screen, side by side, and the human picks one. |
  | `note=<text, file, or link>` | none | Guidance for any step, such as a document on the local or cloud deployment setup. Repeat it for more notes. |

  The step writes the arguments under `## Steering` in the ticket description, with the default for each one not given. A ticket that `factory-plan` creates gets a copy of the plan ticket's `## Steering`. Arguments given to `factory-spec` replace those values on that ticket. Every step reads `## Steering` on its ticket before it starts, and follows the notes that concern it. It reads a file or link in a note when the note concerns its work.
- **Gates.** At a gate, post `🤖 Gate: plan`, `🤖 Gate: spec`, or `🤖 Gate: merge` with a short summary and the question, then stop and ask the human in chat too. The gate is approved when either:
  - the human says "approve" in this chat. Then post `🤖 Approved: <gate> (in chat)` on the ticket, or
  - a human comment on the ticket after the latest gate comment says "approve".

  Any other human reply is feedback: go back to the step before the gate and use it.
- **UI feedback at the merge gate.** For a ticket with the `ui` label, the merge gate is one polish pass against the gallery. A polish fix goes back to `factory-build`, which changes the code and the gallery page in the same PR. Feedback that changes the design goes back to `factory-design` in ticket mode, then through the spec gate again.
- **Writing for humans.** Write every chat message, Linear comment, spec, PR body, and review comment with the `clear-technical-prose` skill. The fixed formats in these rules keep their shape. The prose inside them follows the skill.
- **Chat.** Send a chat message only at the end of a step, at a gate, when blocked, or for a grill or design round in `factory-plan`, `factory-spec`, or `factory-design`. The message gives the result, what you need from the human, and a link. The details go to the Linear ticket and the PR. Do not describe tool calls or progress in chat.
- **Models.** Each step and each subagent runs on the model in `.claude/models.md`:

@.claude/models.md

- **Subagents.** Run verify, CI polling, and log reading in a subagent, on the model from `.claude/models.md`. The subagent returns pass or fail. For a fail it returns the error and the file. Do not paste tool output into chat.
- **Retries.** At most 3 failed attempts per step. Then move the ticket to **Needs human**, comment what was tried and what blocks, and tell the human.
- **GitHub.** Use the session's built-in GitHub connection; no extra token is needed. Use `gh api` with REST endpoints only. The cloud sandbox blocks GitHub's GraphQL API, so `gh pr ...` commands fail there.
- **Git.** Branch `<team lowercase>-<num>/<slug>`, e.g. `librag-12/version-endpoint`. PR title `[<TEAM>-<num>] <title>`. Every commit ends with the trailer `Factory-Issue: <TEAM>-<num>`. Never push to the base branch. Never commit secrets.
