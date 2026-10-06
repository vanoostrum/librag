---
name: fix-ci-failure
description: Diagnose current factory PR verification failures, repair within a durable attempt cap, and leave the issue in Verifying or escalate.
---

# fix-ci-failure

## Purpose
Restore current verification without weakening the required checks.

## Inputs
Failed workflow run, open factory PR/current head, issue/spec, check configuration and any applicable project adapter.

## Outputs
Fix commit, one justified infrastructure rerun, or escalation.

## Done criteria
Failure belongs to the current PR head, root cause is recorded, and an owned fix is pushed without bypassing checks.

## Steps
1. Apply the event contract and acquire ownership. Ignore stale/main/closed/unrelated runs. A spec PR failure can be repaired while preserving Spec review/Specifying; never advance it to implementation review.
2. Count durable ci-fix attempt records, including failed attempts without commits. At three, escalate before another attempt. Read the first real error with `gh run view <id> --log-failed` or the equivalent tool.
3. For factory failures, run `factory/scripts/validate_factory.py` and the policy tests. For application failures, use the actual project verify adapter. Never guess commands from an empty repository.
4. For infrastructure/flaky failures rerun once, then escalate on repetition. For code/config/lint failures repair the cause; do not disable checks or tests.
5. Commit with ci-fix trailers and preserve the correct issue state. Reconcile latest checks after pushing; report attempt and outcome.

## Escalation
Shared escalation for exhausted retries, baseline failures or missing verification/access.

## Reporting
Stage `ci-fix`; routine detail in the log channel, human thread updates on escalation.
