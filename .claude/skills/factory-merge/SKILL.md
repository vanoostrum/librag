---
name: factory-merge
description: Factory step 4. Merge an approved factory pull request and close the Linear ticket. Use after the merge gate is approved.
---

# factory-merge

Read the factory config and rules in `CLAUDE.md` first.

## Input

A ticket whose merge gate is approved.

## Steps

1. **Check the gate.** The merge gate must be approved, and no commits may have been pushed after the `🤖 Gate: merge` comment. If there were, go back to `factory-review`.
2. **Check CI.** The required check must be green on the PR's latest commit (`gh api repos/<repo>/commits/<head sha>/check-runs`).
3. **Merge**: `gh api -X PUT repos/<repo>/pulls/<num>/merge -f merge_method=squash -f sha=<head sha> -f commit_title="<PR title> (#<num>)" -f commit_message="Factory-Issue: <TEAM>-<num>"`. Then delete the branch: `gh api -X DELETE repos/<repo>/git/refs/heads/<branch>`.
4. Move the ticket to **Done** and comment `🤖 merge: success — <merge commit url>`.
5. Tell the human in chat: what shipped, with the PR link.

## Done when

The PR is merged and the ticket is Done.

## Escalation

If the merge fails (conflict, check not green), follow Retries in `CLAUDE.md`. Fix conflicts in `factory-build`.
