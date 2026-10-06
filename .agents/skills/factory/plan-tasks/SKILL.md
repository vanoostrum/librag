---
name: plan-tasks
description: Map a spec to small ordered tasks with acceptance-criterion coverage and appropriate behavioral or document evidence.
---

# plan-tasks

## Purpose
Create independently verifiable steps for the approved scope, without assuming a particular stack or interface.

## Inputs
Spec ACs/design notes, existing repo layout and current readiness boundary.

## Outputs
`1. [ ] T1: <one change> (verifies: AC1) — evidence: <test or document/config check>` under Task plan.

## Done criteria
Every AC maps to a task and proof. Changes are small and ordered by dependencies. Runtime behavior names meaningful tests; documentation names relevant file/config evidence.

## Steps
1. List ACs and identify relevant seams: domain logic, API/transport, persistence, integrations, documentation or configuration, as applicable.
2. Order dependent steps, roughly one reviewable change per task. Split tasks that cannot be verified independently.
3. Check AC coverage and scope. Do not add application scaffolding, architecture, or publishing to a factory-only spec.

## Escalation
Return an untestable or unclear AC to the caller rather than inventing proof.

## Reporting
The calling stage reports; this helper does not start a separate mutating run.
