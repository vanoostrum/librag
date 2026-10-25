---
name: factory-review
description: Factory step 3. Review a factory pull request against its spec in a fresh agent, then stop at the merge gate. Use when a factory PR has green CI.
model: opus
---

# factory-review

Read the factory config and rules in `CLAUDE.md` first. Then load the `bstack` skill with the Skill tool, before any pstack skill.

## Input

A ticket with an open PR and a green required check.

## Steps

1. Move the ticket to **In Review**.
2. **Review in a fresh agent.** Start a subagent on the `fresh reviewer` model from `.claude/models.md`, so the review is not biased by having written the code. Give it only the ticket key and PR number, and this task:

   > Load the `bstack` skill first. Read the `## Spec` of the Linear ticket and the PR diff. For each acceptance criterion, answer met / not met, with evidence (test name, file and line). Check that the PR's **App evidence** covers every route that the PR adds or changes, and that its output matches the criteria. Look at the screenshots on the Linear ticket. Missing or wrong app evidence is a real problem. Check that the tests follow the test seam rule in `CLAUDE.md`: a unit test that only repeats a route test is a real problem. Then list real problems only: bugs, missing tests, security issues, changes outside the scope. No style nitpicks; ruff and ty handle those. Write the review with the `clear-technical-prose` skill. End with PASS or FAIL.

3. **Post the review** as a PR comment. Do not repeat it in chat.
4. **If FAIL:** go back to `factory-build` with the review as input. That counts as a failed attempt for review.
5. **If PASS:** post `🤖 Gate: merge` on the ticket with the PR link and the criteria table. In chat, ask for approval with the PR link and the review link. Stop.

## Done when

The PR has a review comment ending in PASS and the ticket has a `🤖 Gate: merge` comment.

## Escalation

After 3 FAILs, follow Retries in `CLAUDE.md`.

## Next

After approval, continue with `factory-merge`.
