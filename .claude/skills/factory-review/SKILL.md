---
name: factory-review
description: Factory step 3. Review a factory pull request against its spec in a fresh agent, then stop at the merge gate. Use when a factory PR has green CI.
---

# factory-review

Read the factory config and rules in `CLAUDE.md` first.

## Input

A ticket with an open PR and a green required check.

## Steps

1. Move the ticket to **In Review**.
2. **Review in a fresh agent.** Start a subagent so the review is not biased by having written the code. Give it only the ticket key and PR number, and this task:

   > Read the `## Spec` of the Linear ticket and the PR diff. For each acceptance criterion, answer met / not met, with evidence (test name, file and line). Then list real problems only: bugs, missing tests, security issues, changes outside the scope. No style nitpicks; ruff and ty handle those. Write the review with the `clear-technical-prose` skill. End with PASS or FAIL.

3. **Post the review** as a PR comment.
4. **If FAIL:** go back to `factory-build` with the review as input. That counts as a failed attempt for review.
5. **If PASS:** post `🤖 Gate: merge` on the ticket with the PR link and the criteria table. Ask the same in chat. Stop.

## Done when

The PR has a review comment ending in PASS and the ticket has a `🤖 Gate: merge` comment.

## Escalation

After 3 FAILs, follow Retries in `CLAUDE.md`.

## Next

After approval, continue with `factory-merge`.
