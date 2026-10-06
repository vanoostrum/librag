---
name: bootstrap-project-skills
description: Inspect an already initialized project to derive and verify its stack verification adapter; do not scaffold an application or create publishing adapters when disabled.
---

# bootstrap-project-skills

## Purpose
Make project craft swappable after project setup, without guessing commands.

## Inputs
Existing manifests, task runners, CI, supplied architecture and AGENTS.md; explicit authorization for step 3.

## Outputs
A project `verify-*` skill with prerequisites, fast/full checks, single-test command, local/CI boundaries, logs and common failures; verified command evidence in a PR.

## Done criteria
Commands came from the real project and have passed locally or in named CI jobs. Frontmatter and references validate. No publishing adapter is created in the current scope.

## Steps
1. During factory-only setup, return deferred without generating project skills. At step 3 inspect actual manifests/CI and preserve the human's architecture and notes.
2. Extract install/build/lint/test commands and exercise them. Record local results and exact CI-only evidence; an unexecuted guessed command is not verified.
3. Write/update only the required verification adapter and project required-check mapping. Run generic factory validation as well.
4. Promote readiness to 3 only after the adapter, application CI and human review are complete. Publishing remains disabled.

## Escalation
If project setup/CI is absent, report the concrete prerequisite and leave application automation paused. Do not create placeholder skills claiming verification.

## Reporting
PR lists the actual commands and successful evidence; standard factory records apply when invoked for a tracked item.
