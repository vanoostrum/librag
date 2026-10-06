---
name: implement-task
description: Implement an approved factory spec or claimed review-feedback cycle, verify appropriate evidence, and open or update its implementation PR.
---

# implement-task

## Purpose
Turn approved scope into a mergeable PR, within the configured readiness boundary.

## Inputs
Issue, approved spec on default branch and its SHA, shared rules; project verify adapter only for application work at readiness 3.

## Outputs
Implementation branch/PR, AC evidence, issue in Verifying. Review mode also replies to the owned findings.

## Done criteria
Approved tasks are complete, AC evidence exists, applicable current checks pass locally, and the PR links issue/spec/thread with `Factory-Kind: implementation` and approved spec SHA.

## Steps
1. Read common rules, verify approved spec and state, deduplicate and acquire ownership. Reject spec PRs in review-comments mode.
2. At readiness 1 allow only factory/docs changes. At readiness 2 keep application automation paused. At readiness 3 application work needs real project verification commands/checks. Never replace missing verification with generic contract checks.
3. Continue the existing branch/PR on retries. For runtime code write meaningful tests first; for documents/config implement the AC evidence plan. Validate contracts and, when applicable, run the project adapter. Commit small changes with `build` or `comment-fix` trailers.
4. Update the task checklist and PR evidence. In review mode address only the owned feedback cycle, reply once per finding, and invalidate the old gate approval after changing the head.
5. Move to Verifying before releasing ownership. Reconcile any CI event that arrived early by querying the latest head's checks; do not depend on a lost trigger.

## Escalation
Shared cap/access escalation. Do not weaken checks, silently change the spec, or invent the human's application architecture. Application requests queued for later steps stay Triage.

## Reporting
Shared reporting, stage `build` or `comment-fix`.
