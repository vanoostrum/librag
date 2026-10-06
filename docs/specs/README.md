# Specs

One spec per work item. Use the actual Linear team key from `factory/linear.yaml`.
Filename: `<KEY>-<num>-<slug>.md`. Spec branch: `<key>-<num>/<slug>-spec`.
Implementation branch: `<key>-<num>/<slug>`.

Lifecycle: spec PR → revision-bound human Gate 1 → merged approved spec → implementation PR → evidence review → revision-bound human Gate 2 → confirmed merge → Done. No publishing is implied.

At readiness 1 only docs/factory tasks are eligible. Application work is queued until the later setup and verification steps. Documentation criteria use file/config evidence and contract validation; runtime behavior requires tests once project verification is enabled.

## Template

```markdown
# <KEY>-<num>: <Title>

- Linear: <issue URL>
- Slack thread: <permalink>
- Work kind: factory-docs | application
- Type: feature | bug | chore
- Risk: low | high

## Context
Quote the request and explain the intended outcome.

## Scope
Concrete changes and the current readiness boundary.

## Non-goals
Explicit scope exclusions. Publishing and product architecture are excluded from factory setup.

## Acceptance criteria
- [ ] AC1: Given …, when …, then …

## Design notes
Affected existing files and configuration. Refer to supplied architecture; do not invent it.

## Evidence plan
For each AC: file/config evidence for documentation, or a behavioral test for runtime code.

## Risks
Relevant failure modes and mitigations.

## Task plan
1. [ ] T1: <change> (verifies: AC1) — evidence: <test or document/config check>
```
