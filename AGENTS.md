# AGENTS.md

**LibRag** is intended to be a Python/FastAPI project. This repository currently contains its software factory, not the application. Cursor runs the factory through Slack, Linear, and GitHub. A human approves the spec and the merge.

## Scope and sequencing

1. **Factory first (current):** integrations, automations, and contracts. Exercise the lifecycle with documentation or configuration work.
2. **Initial project setup (later):** the human supplies an existing architecture and project plan. Do not invent or overwrite them. The human runs Docker locally.
3. **Project verification (later):** derive build/lint/test commands and `verify-*` skills from the implemented project and CI.

Publishing, hosting, image pushes, release credentials, and deployment are out of scope. `Done` means an approved implementation PR was merged and reported.

## Flow

1. **Front desk** (`.agents/skills/factory/front-desk`) handles every message and ✅ reaction in #librag. It starts or links a Linear issue, questions the human until the acceptance criteria are clear, writes the spec into the issue, and takes the approval. Approval moves the issue to Building.
2. **Build** (`implement-task`) implements the spec and opens a PR. The issue moves to Verifying.
3. **CI fix**, **review**, and **comment fix** get the PR to green and reviewed. Review posts the merge gate. The issue moves to Ready to merge.
4. **Front desk** merges on approval. **Merge completed** reports it and sets Done.

| Path | Purpose |
|---|---|
| `factory/config.yaml` | Repo, Slack channels, readiness, approvers, checks, models. |
| `factory/linear.yaml` | LibRag team, state, and label IDs. |
| `factory/stages.yaml` | Stage triggers and transitions. |
| `factory/automations/` | Cursor automation bindings. |
| `factory/scripts/guard_store.py` | Shared claim and receipt store. |
| `factory/scripts/spec.py`, `pr.py`, `merge.py` | Spec section updates, branch/commit/PR conventions, and the guarded merge. |
| `.agents/skills/factory/` | Stage skills. |
| `SETUP_LOG.md` | Live resource IDs and verification evidence. |

## Runtime rules

These apply to every stage.

- **Rebuild context.** Each automation run starts fresh. Read the current state from Slack, Linear, and GitHub, not from the event payload or memory.
- **Bindings.** Act only on `vanoostrum/librag`, the LibRag Linear team, and #librag. IDs are in `factory/config.yaml` and `factory/linear.yaml`. Ignore bot messages and #librag-log.
- **Claim before changing anything.** Run `python3 factory/scripts/guard_store.py begin --issue <KEY-num> --stage <stage> --owner <run-id> --event <event-id>`. If it prints `busy` or `duplicate`, stop. `busy` means another run holds the issue, and this event was not recorded. `duplicate` means the event already finished (`success`, `noop`, or `escalated`); `begin` has released the claim. Do the work, then run `record --event <event-id> --stage <stage> --outcome <success|failed|escalated|noop>`, then `release --issue <KEY-num> --owner <run-id>`. A `started` or `failed` receipt can be recorded again, so a crashed or failed run can be retried. A `release` that prints `not-owner` has not cleared the claim. Never force-push `factory-guards`.
- **Readiness.** At step 1, only change factory and docs files. At step 2, the only application work is the initial project setup the human requested, and it may create any project file. Other application requests stay in Triage with `needs-project-setup`. Application implementation needs step 3, a project verify skill, and required project checks.
- **Spec.** The spec lives in the Linear issue description under `## Spec (rev N)` and ends at `<!-- /spec -->`. Headings inside that span stay part of the spec. It is not stored in the repo. Any change increments N.
- **Approvals.** Only Slack users in `approvals.slack_user_ids` can approve. An approval counts only for the latest gate message and its spec revision. A merge approval also binds to the PR head SHA. A later spec change or commit invalidates it. Never merge without a valid approval.
- **Checks.** A required check counts only if it succeeded on the current PR head. Pending, missing, skipped, or neutral is not green.
- **One writer.** Only one stage fixes a given round of review feedback.
- **Retries.** At most three automatic attempts per stage per feedback round, counting failed runs. Then move the issue to Needs human and say what was tried.
- **Reporting.** Short updates go in the item's Slack thread. Detail goes to #librag-log, prefixed `[<KEY>-<num>] <stage>:`. Add one Linear comment per run: `Run record: stage | model | started | finished | outcome | notes`, with an outcome of `success`, `failed`, `escalated`, or `noop`.
- **Git.** Use branch `<key>-<num>/<slug>` with a lowercase key, and PR title `[<KEY>-<num>] <title>`. Commits and the squash merge keep `Factory-Issue: <KEY>-<num>` and `Factory-Stage: <stage>` trailers. Commits, pushes, pull requests, and merges are made as `chef-willie[bot]` (`factory/config.yaml` `github_app`). Never push to `main`, bypass required checks, or commit secrets.
- **Pull requests.** Open and update PRs only with `factory/scripts/pr.py upsert`, never with Cursor's PR tool (`open_git_pr`, ManagePullRequest). PRs are never drafts. If `upsert` fails, record `failed` and stop.

## Verification

`Factory Contracts` validates the factory on every PR. Locally: install `factory/requirements.txt` in a virtual environment, then run `python3 factory/scripts/validate_factory.py` and `python3 -m unittest discover -s factory/tests -v`. This proves nothing about an application.
