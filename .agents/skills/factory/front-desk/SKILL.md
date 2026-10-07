---
name: front-desk
description: Handle a #librag message or reaction. Start or link a work item, question the human until the acceptance criteria are clear, write the spec into Linear, handle approvals, and answer status questions.
---

# front-desk

Each message or ✅ reaction starts a fresh run. Read the Slack thread and its linked Linear issue to see where things stand.

## Start a work item

- **New request** in a top-level message: create a LibRag issue in Triage. Quote the request and add `Slack-Thread: <permalink>`.
- **Existing issue** named in a top-level message (`LIBRAG-12` or its URL): use that issue and its description as the request. Add `Slack-Thread: <permalink>` to it. If it is already linked to another thread, reply with that thread's link and stop.
- **Status question:** answer from Linear. Create and change nothing.
- **Application work** below readiness 3: add `needs-project-setup`, leave it in Triage, explain why in the thread, and stop.

## Question the human

Aim for a functional spec that the implementer and reviewer can test against. Ask about behavior and acceptance criteria, not technical design.

- Ask the questions that matter most for implementation and testing: scope, expected behavior, important edge cases, and what done looks like. Number them and ask them together.
- Do not assume answers to these. Keep asking until the important unknowns are settled.
- Leave small technical or functional details to the implementer.
- If the human says to go ahead with open questions, record them in the spec as assumptions.

## Spec and approval request

Replace the spec section of the issue description:

```
## Spec (rev N)
Goal:
Acceptance criteria:
1.
Out of scope:
Assumptions:
```

Increment N on every change. Post a short summary in the thread with the goal, acceptance criteria, out of scope, revision, and issue link. End it with: "React ✅ or reply approve to start implementation." Add a Linear comment `Gate: spec rev N, message <ts>`.

## Approvals and feedback

A ✅ or an approve reply counts only if it comes from a configured approver and refers to the latest gate message, and that gate message's revision still matches the issue.

- **Spec gate:** move the issue to Building.
- **Merge gate** (Ready to merge): confirm that the gate's head SHA is still the PR head and that the required checks are green. Squash-merge with the trailers, then confirm the merge on GitHub. Leave the state for merge-completed.
- **Feedback instead of approval:** at the spec gate, revise the spec as a new revision and ask again. At the merge gate, add the feedback to Linear and move the issue to Building.
