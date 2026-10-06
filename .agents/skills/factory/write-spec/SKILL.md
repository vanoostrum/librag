---
name: write-spec
description: Turn an eligible factory issue into a spec and task plan, open or update its spec PR, and establish the first revision-bound human gate.
---

# write-spec

## Purpose
Produce a concrete, reviewable contract for the requested work without changing product scope.

## Inputs
Issue and feedback, supplied repo knowledge, `docs/specs/README.md`, shared config and event contract.

## Outputs
Spec file, existing-or-new spec PR, durable Gate 1 record and Slack approval message; issue in Spec review.

## Done criteria
ACs are observable, each has evidence and tasks, non-goals are explicit, the PR is correctly typed, and the gate binds the current head.

## Steps
1. Read shared rules, verify Specifying and readiness eligibility, deduplicate and acquire ownership. Do not spec new product architecture during factory setup.
2. Reuse the existing spec branch/PR after feedback. Ground changes in actual files and the request. Use `plan-tasks` for the task plan.
3. Commit with spec trailers. Open/update `[<KEY>-<num>] Spec: <title>` from `<key>-<num>/<slug>-spec` with `Factory-Kind: spec`, issue and Slack link.
4. Run generic contract checks; wait for current required checks before an approval merge. Invalidate any prior gate record after changes.
5. Establish the Gate 1 record and Spec review state, then post scope, key ACs, PR URL and revision in the item thread. Store the message timestamp before releasing ownership; approvals cannot operate on an incomplete gate record.

## Escalation
Use shared escalation for conflicting requirements, access gaps or capped failed attempts. Queue application work while readiness is insufficient.

## Reporting
Shared reporting, stage `spec`.
