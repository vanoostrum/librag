---
name: write-release-notes
description: Report confirmed approved implementation merges and close their issues in merge-completion mode; release publishing mode is disabled.
---

# write-release-notes

## Purpose
Close the current no-publishing lifecycle with accurate merge information.

## Inputs
Merged implementation PR event, Gate 2 record, issue/spec and confirmed GitHub merge/head SHAs.

## Outputs
Short completion notes in the issue thread, merge evidence/run record, issue in Done.

## Done criteria
The exact approved implementation was merged; reporting is complete and idempotent. No local execution or publishing claim is made.

## Steps
1. Read shared rules and require **merge-completion mode**. Publishing mode and release workflow events return noop while disabled.
2. Ignore spec PRs, unrelated repos, open/unmerged PRs, and duplicate completed events. Acquire issue ownership and resolve the durable Gate 2 record, even if the tracker transition raced the GitHub event.
3. Verify approval matched the merged head and approved spec; confirm GitHub merge SHA and issue attribution. Unauthorized/manual unapproved factory merges escalate rather than silently closing.
4. Record merge SHA and draft concise completion/inspection notes from the ACs. Post once: `<KEY>-<num> merged: <PR URL> (<merge SHA>). <what changed / how to inspect>`. Publishing and local execution remain unverified/out of scope.
5. Reconcile previously posted notes on retry. Record outcome and move only this issue to Done after reporting succeeds. Never rediscover all open issues as shipped work.

## Escalation
Missing approval, attribution or reporting access follows common escalation. A reporting retry must not re-merge the PR.

## Reporting
Shared reporting, stage `merge-completed`.
