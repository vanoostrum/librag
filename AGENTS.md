# AGENTS.md

**LibRag** is intended to be a Python/FastAPI project. This repository currently contains its reusable software factory, not the application. Cursor executes the factory through Slack, Linear, and GitHub, with human spec and merge gates.

## Scope and sequencing

1. **Factory first (current):** configure integrations, automations, and generic contracts. Exercise the lifecycle with documentation/configuration work.
2. **Initial project setup (later):** the human supplies an existing architecture and project plan. Do not invent or overwrite them. The human owns local Docker operation.
3. **Project verification (later):** derive actual build/lint/test commands and `verify-*` skills from the implemented project and CI.

Publishing, hosting, image pushes, release credentials, and deployment are out of scope. `Done` means an approved implementation PR was merged and its completion was reported, not that an application was shipped.

## Where things live

| Path | Purpose |
|---|---|
| `docs/factory-setup-prompt.md` | Execute this runbook in Cursor to configure the factory. Reuse these files. |
| `docs/librag-factory-migration-plan.md` | Migration decisions and boundaries. |
| `docs/specs/` | Issue specs and acceptance-criteria template. |
| `docs/adr/` | Factory decisions. |
| `docs/architecture.md` | Handoff boundary for the human's existing architecture; no product design here. |
| `factory/stages.yaml` | Stack-neutral stage contracts. |
| `factory/config.yaml` | Repo, Slack bindings, readiness, approvals, check names, and model mapping. |
| `factory/linear.yaml` | New LibRag team, workflow state/label IDs; Cursor populates nulls. |
| `factory/automations/` | Cursor automation definitions derived from stages. |
| `factory/event-contract.md` | Replay, ownership, current-check and approval rules shared by all stages. |
| `factory/scripts/` | Generic contract validation; this is not application verification. |
| `.agents/skills/factory/` | Eight copied and adapted factory skills. |
| `.agents/skills/project/` | Deferred until step 3; no working project adapter exists yet. |
| `SETUP_LOG.md` | Fresh setup checklist, resource IDs, capability checks, and smoke-test evidence. |

## Factory conventions

- Repository: `vanoostrum/librag`. Linear team: **LibRag**, proposed key **LIBRAG**; always read the actual key from `factory/linear.yaml`.
- Slack interface: **#librag**; log: **#librag-log**. Channel IDs are configured at setup. Do not route requests to another project's factory.
- Branch: `<key>-<num>/<slug>` (lowercase issue prefix); spec branches end in `-spec`. Setup branch: `codex/factory-setup`.
- PR title: `[<KEY>-<num>] <title>`. PR body includes `Factory-Kind: spec|implementation`, issue, approved spec SHA, Slack thread, and AC evidence.
- Every factory commit, including the squash merge commit, carries `Factory-Issue: <KEY>-<num>` and `Factory-Stage: <stage>` trailers.
- Run record: `Run record: stage | model | started | finished | outcome | notes`, where outcome is `success`, `failed`, `escalated`, or `noop`. Include event ID, PR/head SHA, spec SHA, and attempt number in notes. Count failed runs even if no commit was made.
- Store `Slack-Thread: <permalink>` in each Linear issue. Short updates go in that thread; details go to the configured log channel.
- At most three automatic repair attempts per stage/feedback cycle, then **Needs human**. Clarification is capped at two rounds.
- One active mutating run per issue/branch. Read `factory/event-contract.md` before any stage operation. Never rely on a prompt or a run comment as an atomic lock.
- Never merge without current human approval bound to the PR head and spec revision. Never push directly to `main`, bypass required checks, or commit secrets.

## Current verification boundary

`Factory Contracts` validates the factory configuration and skills for every PR. Run `python3 factory/scripts/validate_factory.py` and `python3 -m unittest discover -s factory/tests -v` after installing `factory/requirements.txt` in an isolated environment. Runtime validation uses `--runtime` once Cursor has populated bindings and capability evidence.

This check proves nothing about an application. At readiness 1, work is limited to factory/docs changes. Application requests stay in Triage. At readiness 2, initial application setup is performed as a separately authorized task; application factory builds stay paused. Only readiness 3 plus a real project verification adapter and required CI check permits automated application implementation.
