# Shared runtime event contract

Read this before every stage. Resolve current facts from Slack, Linear and GitHub; event payloads and automation memory can be stale. Instance bindings come from `factory/config.yaml` and `factory/linear.yaml`.

## Routing and preconditions

Require the configured repo/team/channel and exact issue/PR association. Ignore bots for Slack intake and approvals. PR bodies contain `Factory-Kind: spec|implementation`; branch suffix `-spec` must agree with the kind. Spec PRs never enter implementation review, comment-fix, or completion handling. Unknown/mismatched kind escalates without a state transition.

Process top-level status/control messages before treating a message as new work. Store intake identity as `(channel_id, root_thread_ts)` and create one Triage issue before clarification. At readiness 1 allow factory/docs-only work; queue application requests in Triage with `needs-project-setup`. Initial project setup is a separate human-authorized task at step 2. Application automation requires readiness 3 and a real verification adapter.

## Receipts, ownership and retry counts

Canonical identities: Slack event ID (fallback channel/message/reaction timestamp plus actor/type); Linear event ID plus state revision; GitHub delivery ID plus PR/head SHA/workflow attempt/comment ID. Persist receipts using the configured durable mechanism. One intake thread maps to one issue. A completed receipt returns noop, without repeated side effects.

Enforce one active mutating owner per issue/branch with an atomic claim in a shared mechanism, not local agent files, memory, or unguarded Linear comments. Claim includes event ID, stage, owner/run ID and expiry; stale claims are reconciled against the actual run before recovery. Every stage, including front desk, build, fix, review and completion, uses the same mechanism. Never release another run's claim.

Cursor setup must prove native serialization/deduplication for these overlapping triggers, or configure a minimal shared guard adapter using an atomic store. Do not introduce application infrastructure to solve this. Record the chosen mechanism and replay/concurrency evidence. If no reliable mechanism is available, keep mutating automations disabled and report the concrete capability blocker; a prompt is not a lock.

`factory/scripts/policy.py` supplies pure guard decisions over freshly queried facts. It implements no API access, durable receipts or atomic claims. `factory/scripts/guard_store.py` is the shared adapter: claims and receipts live in `state.json` on `refs/heads/factory-guards`, updated only by a fast-forward push. A rejected push is a lost compare-and-swap; re-read and retry. Do not force-push that ref. Acquire a claim and record a started receipt before side effects, then enforce the policy decision. The same ref is the receipt log. A duplicate event id returns noop. A waiting event must be durably queued/retried or reconciled by the active owner after releasing its claim; do not discard an early CI, approval or merge event because another run held the lock.

Before each automatic repair, count attempts from durable run records for `(issue, stage, feedback-cycle)`, including failed/no-commit runs. Record a started receipt before the attempt, then its outcome. At three attempts, escalate without starting a fourth. Do not count ignored duplicates as attempts. Spec refinement and reviewer feedback cycles need explicit revision/cycle IDs.

## CI and review

For CI events, compare event SHA to current PR head; ignore stale/canceled/unrelated runs. Query every required check for that head: generic factory checks always, plus project checks for application work at readiness 3. Pending, missing, skipped, failed or neutral required checks are not green. Ignore `main` push runs as implementation-review triggers. Only open implementation PRs with an approved spec may enter review.

Review may send an issue to Building, or a comment-fix handler may own a feedback cycle, but not both. Record findings and owner before triggering a transition. Ignore non-actionable bot replies, resolved/stale comments, and comments already addressed. Do not enable competing autonomous fix tools until this ownership is verified.

## Gate approvals and merges

Durable gate record fields: issue ID, gate, PR number, current head SHA, approved spec SHA, Slack gate message timestamp, creation time, approver identity, approval event ID and approval time. Configure named approvers in `config.approvals.slack_user_ids`. Approval is only a reaction on that gate message or an exact approval reply explicitly referencing that gate message. Bare approval text is accepted only if that thread has exactly one current pending gate and the reply follows it. State alone is insufficient. Reject old/ambiguous gate events.

Publish the record and set the waiting state before posting the gate message; serialize the final message timestamp update so no approval is consumed while the record is incomplete. Re-check PR/spec revisions and all required checks under the run claim immediately before merging. Any relevant new commit or feedback invalidates the old approval. A formal automated PR review is not a human gate approval.

Squash-merge with an explicit body preserving `Factory-Issue` and `Factory-Stage` trailers. Confirm merged status and merge SHA from GitHub. No force/admin bypass. If checks are pending, remain at the gate; auto-merge may be scheduled only if later revisions cannot reuse stale approval. Gate 1 starts Building only after the spec merge is confirmed. Gate 2 remains Ready to merge until merge-completed confirms the implementation merge. No Shipping state is used.

## Completion

Reconcile the GitHub merged PR with the durable Gate 2 record and issue. Verify the approved head was merged and retain the merge SHA, PR URL and spec SHA. Send a completion message for that exact issue; record success and then move it to Done. Retry missing reporting without merging again or duplicating a previous post. If an unauthorized merge is observed, escalate rather than treating it as a successful gate. Never infer local Docker execution or publishing from the merge.
