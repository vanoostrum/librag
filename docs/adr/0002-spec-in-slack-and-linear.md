# ADR 0002: Triage and spec happen in the Slack thread, and the spec lives in Linear

- Status: Accepted
- Date: 2026-10-07

## Context

Separate Specifying and Spec review stages, spec PRs, a planning skill, and a shared event contract file added steps and instructions without improving the result. Rules in files other than `AGENTS.md` are not loaded automatically.

## Decision

- Front desk handles intake, questioning, the spec, and spec approval in one Slack thread. A request can start as a new #librag message or as a #librag message that references an existing Linear issue.
- Questioning covers functional behavior and acceptance criteria. It asks about the unknowns that implementation and testing depend on, and leaves small details to the builder.
- The spec is written to the Linear issue description as `## Spec (rev N)`. A ✅ reaction or an explicit approval reply on the latest summary moves the issue straight to Building. No spec PR exists.
- Shared runtime rules live in `AGENTS.md`. The `write-spec` and `plan-tasks` skills, `factory/event-contract.md`, and the spec automation are removed.

## Consequences

- Workflow: Triage → Building → Verifying → Reviewing → Ready to merge (merge gate) → Done.
- Approvals bind to the spec revision and the gate message. A merge approval also binds to the PR number and head SHA.
- The Specifying and Spec review states remain unused in Linear.
