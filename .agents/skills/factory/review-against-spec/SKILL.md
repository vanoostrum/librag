---
name: review-against-spec
description: Review an implementation PR after complete current-head CI, map acceptance criteria to evidence, and establish Gate 2 or a single owned feedback cycle.
---

# review-against-spec

## Purpose
Independently verify approved scope using a model from a different vendor than the builder.

## Inputs
Implementation PR/head, approved spec SHA, issue, complete required check set and common event contract.

## Outputs
AC evidence table and findings; Ready to merge with Gate 2 record, or Building with one assigned feedback cycle.

## Done criteria
Every AC has evidence; findings distinguish blocking and optional; no spec PR or stale/partial CI event changes implementation state.

## Steps
1. Apply common guards. Explicitly return noop for spec PRs. Require Verifying/Reviewing, approved spec, current event/head SHA and every required check successful. Acquire ownership, then move the issue to Reviewing.
2. Count durable review feedback cycles; after three unsuccessful cycles escalate. Check the full AC set against the latest diff, including previously satisfied behavior affected by new commits.
3. Runtime ACs require tests; docs/config ACs use the approved evidence plan and generic contract check. Check non-goals, privacy/security, conventions and attribution.
4. Post one review with `AC | met? | evidence`, and labeled findings. If blocking, record a new feedback cycle and assign Building as its single writer before transitioning. Comment-fixer must not also launch that cycle.
5. If satisfied, create the durable Gate 2 record for this head/spec, set Ready to merge and post the gate message with PR URL and revision; store its timestamp. Preserve current-head checks and approval invalidation rules.

## Escalation
Shared escalation for cap, invalid spec or missing evidence/access.

## Reporting
Shared reporting, stage `review`.
