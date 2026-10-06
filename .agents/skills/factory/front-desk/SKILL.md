---
name: front-desk
description: Handle configured factory Slack intake, clarification, status, feedback and revision-bound human approvals; never perform stage implementation.
---

# front-desk

## Purpose
Translate human conversation into tracker state and protected gate merges.

## Inputs
Slack event, current issue/PR facts, and the shared configuration and event contract.

## Outputs
One intake issue per root thread, status/feedback replies, gate records and confirmed spec/implementation merges.

## Done criteria
The event has one recorded outcome; controls create no accidental work item; merges require a configured approver and current gate revision.

## Steps
1. Read the shared README and event contract. Validate bindings, deduplicate the event and acquire run ownership before mutations. Ignore bot Slack events and the log channel.
2. Classify **status first**, then approval, existing-thread feedback/clarification, then new intake. Status queries summarize open issues without creating an issue or changing state.
3. For new intake, look up `(channel, root_thread_ts)` before creation. Create one issue in Triage with the quoted request, `Slack-Thread: <permalink>`, type/risk labels, `Factory-Work-Kind: factory-docs|application`, and intake identity. If clarification is needed, store the question/round on that issue and ask in the thread, at most two rounds. Follow-up replies resume the same intake.
4. At readiness 1, application requests stay Triage with `needs-project-setup`. Explain the later setup/verification boundary. Ready docs/factory requests transition to Specifying. Initial product architecture and plan creation are outside this task.
5. Approval: resolve the exact current gate record, authorize the Slack user, verify message timestamp, PR/head/spec revision and complete checks. Reject ambiguous/stale approvals and state mismatches. For Spec review, squash-merge the spec with trailers and confirm GitHub merged it, then set Building. For Ready to merge, preserve trailers, merge only with current checks and confirm the merge; leave the state for merge-completed to reconcile. No publishing action follows.
6. Feedback at a gate invalidates its approval record. Add `Feedback from Slack: <text>` to Linear; return to Specifying or Building under a new feedback cycle. Non-gate replies append relevant context. Resume paused intake only when readiness allows it.
7. Record receipts, outcome and reporting under the common rules; release your own claim.

## Escalation
Unmatched approvals are explained without merging. Conflicts/protection failures or lost ownership escalate. A pending check leaves the issue at its gate.

## Reporting
Shared reporting, stage `front-desk`. Log unchanged status replies as receipt outcomes without unnecessary tracker chatter.
