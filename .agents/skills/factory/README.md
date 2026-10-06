# Factory skills

The eight stage contracts are reused from the source factory. They are stack-neutral. Shared state, binding and reporting rules live here and in `factory/event-contract.md`; each skill must read them before acting.

## Shared inputs

- `factory/stages.yaml`: stage contracts, caps and enabled flags.
- `factory/scripts/guard_store.py`: shared claim and receipt ref. Run it before mutating.
- `factory/config.yaml`: channels, repository, readiness, approvers, required checks, models and verified runtime mechanisms.
- `factory/linear.yaml`: team key and real resource IDs.
- `AGENTS.md`: current scope and branch/PR conventions.

## Common reporting

1. Short human updates go into the configured item thread (`Slack-Thread:` in the issue); logs go into the configured log channel, prefixed `[<KEY>-<num>] <stage>:`.
2. Append `Run record: <stage> | <model id> | <started ISO> | <finished ISO> | <success|failed|escalated|noop> | <notes>`. Notes carry event ID, issue, PR/head/spec SHA, feedback cycle and attempt. Record failed attempts without commits.
3. Commits and squash merges preserve `Factory-Issue: <KEY>-<num>` and `Factory-Stage: <stage>`. Branches use the configured lowercase key; PRs link the issue, spec and thread.
4. Stage outputs and receipt records are reconciled on retry. Replayed events are noop; do not post the same message twice.

## Common escalation

At the cap, missing access, or an unresolved human decision: release your own run claim, move the issue to Needs human, post what was tried and what blocks progress, and record `escalated`. Preserve receipts and evidence. A request deliberately queued for a later readiness step remains Triage rather than being classified as a failure.

## Verification and completion boundary

Factory/docs tasks use `Factory Contracts` and AC-specific document/config evidence. Application tasks require a working `project/verify-*` adapter and application CI after readiness 3; no missing command may be silently treated as passing. `write-release-notes` currently runs only in merge-completion mode. Publishing stages are disabled.
