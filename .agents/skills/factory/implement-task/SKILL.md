---
name: implement-task
description: Implement the approved spec from the Linear issue and open or update its pull request. Also fixes an owned round of review feedback.
---

# implement-task

The input is an issue in Building with an approved `## Spec (rev N)` in its description.

1. Work on `<key>-<num>/<slug>`. On a retry, continue the existing branch and PR.
2. Implement against the acceptance criteria. Decide small details yourself. If a criterion cannot be met or contradicts the codebase, ask in the thread and move the issue to Needs human. Do not change the scope yourself.
3. Prove each criterion. Use tests for runtime behavior and a file or config check for documentation and configuration. Run the factory validation.
4. Open or update the PR. Its body lists the issue, spec revision, Slack thread, and an `AC | evidence` table. Move the issue to Verifying.

**Review feedback mode:** address only the findings this run owns. Reply once per finding, then move the issue to Verifying.
