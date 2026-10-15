---
name: factory-build
description: Factory step 2. Implement an approved spec with tests first, verify it, and open a pull request. Use after the spec gate is approved, or when CI fails on a factory PR.
---

# factory-build

Read the factory config and rules in `CLAUDE.md` first.

## Input

A ticket whose spec gate is approved.

## Steps

1. **Check the gate.** The spec gate must be approved. If not, stop and say so.
2. **Branch.** Create or check out the branch from the naming rule, based on the latest base branch. Set the bot git identity.
3. **Per task in the plan:**
   1. Write a failing test for it.
   2. Make it pass with the smallest change.
   3. Run the full verify (see the verify skill from the config). Fix until green.
   4. Commit with the `Factory-Issue` trailer.
4. **Check the acceptance criteria.** Each one must be covered by a test, or explain in the PR why it cannot be.
5. **Open the PR** as the bot user, against the base branch. If a PR for the branch already exists, push to it. The PR body has:
   - a one-line summary and the Linear ticket link;
   - a table of acceptance criteria → evidence (test name or file).
6. **Wait for CI.** Watch the required check with `gh pr checks --watch`. If it fails, read the logs, fix, push. That counts as a failed attempt.
7. Comment `🤖 build: success — PR <url>` on the ticket.

## Done when

The PR is open, the required check is green on its latest commit, and every acceptance criterion has evidence.

## Escalation

After 3 failed attempts (verify or CI), follow Retries in `CLAUDE.md`.

## Next

Continue with `factory-review`.
