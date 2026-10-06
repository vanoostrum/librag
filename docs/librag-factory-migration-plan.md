# LibRag factory migration — Cursor execution plan

Revised 6 October 2026. Supersedes the earlier scaffold-first migration proposal.

## Fixed decisions

- Destination: `vanoostrum/librag`, local `~/projects/vanoostrum/librag`.
- Execution: Cursor, running `docs/factory-setup-prompt.md`.
- Reuse copied `docs/`, `factory/`, `AGENTS.md`, and all eight factory skills rather than generating them again.
- New dedicated Linear team **LibRag**, proposed key LIBRAG; Cursor records the actual ID/key.
- Slack intake **#librag**, logs **#librag-log**; verify the existing workspace before writes.
- Current lifecycle ends at an approved implementation merged and reported. No publishing/deployment/release workflow.
- Product architecture/plan already exist and are outside this task. The human owns local Docker execution later.

## Step 1 — Generic factory, now

Execute the prepared runbook in Cursor. Populate instance bindings, configure integrations/protection/models/approvers, create automations from existing definitions, and exercise both gates using documentation work only.

Prepared assets include a fresh setup log, null destination resource IDs, readiness boundaries, generic Factory Contracts CI, and eight adapted stage skills. Stage and event rules explicitly exclude spec PRs from implementation review, require complete current-head checks, bind approvals to revisions, preserve squash attribution, count failed/no-commit attempts, and reconcile confirmed merges before closing issues.

The automation inventory is front desk, spec, build in docs/factory mode, CI fixer, independent spec reviewer, claimed comment fixer, and merge-completed. The old release-notes automation is disabled. Its existing skill is reused in merge-completion mode.

Shared receipts and atomic per-issue ownership must be verified in the harness or a small guard-state adapter before activating overlapping handlers. Static validators and written contracts do not establish live guarantees. Cursor records the actual mechanism and concurrent/replay probes; missing capabilities leave mutation handlers disabled with a concrete blocker.

Readiness stays 1. Generic docs/config work can traverse the lifecycle. Application requests are saved in Triage with `needs-project-setup`, not sent into a nonexistent application build.

Acceptance: actual LibRag states/labels and Slack channels verified; skills/config available on main; protection applies; named human gates work; one docs-only request reaches Done without publishing; control/replay/stale/failure/cap boundaries have evidence in SETUP_LOG.

## Step 2 — Initial project setup, later

Only on separate authorization, use the human's existing architecture and project plan to initialize Python/FastAPI. Do not invent architecture in the factory setup. Local Docker operation belongs to the human. Application implementation automation remains paused until verification exists.

## Step 3 — Project-specific verification, later

Derive install/build/lint/test commands from the actual project and CI, validate them and add the project `verify-*` adapter and required checks. Use `bootstrap-project-skills` only after this real project exists. Promote readiness to 3 after human review and passing application CI. Publishing remains disabled.

## Execution order inside step 1

1. Read assets; inspect connections and current official docs.
2. Create/reuse the dedicated LibRag team and destination channels; write real bindings.
3. Configure models and named approvers; prove thread/Linear/merge/receipt/serialization capabilities.
4. Review and merge the setup PR, then apply verified Factory Contracts protection.
5. Create disabled automations from specifications; validate runtime config.
6. Activate handlers and intake last; exercise the docs-only smoke test and boundaries.
7. Record resource IDs/URLs, smoke evidence and unresolved limits; stop before application setup.

## Current preparation versus runtime

The local repository assets have been prepared. Live Linear/Slack/Cursor resources have not been configured by this editing task. `SETUP_LOG.md` distinguishes prepared files from unverified runtime actions. Cursor is responsible for executing the runbook.
