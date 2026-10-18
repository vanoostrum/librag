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
2. **Branch.** Create or check out the branch from the naming rule, based on the latest base branch.
3. **Domain docs.** If the spec has **Domain docs**, write them to `GLOSSARY.md` and `docs/adr/` as the spec says. Commit them with the `Factory-Issue` trailer.
4. **Per task in the plan:**
   1. Write a failing test for it.
   2. Make it pass with the smallest change.
   3. Run the full verify (see the verify skill from the config) in a subagent. Fix until green.
   4. Commit with the `Factory-Issue` trailer.
5. **Check the acceptance criteria.** Each one must be covered by a test, or explain in the PR why it cannot be.
6. **Open the PR** against the base branch. Write the PR body with the `clear-technical-prose` skill. First look for an existing one: `gh api "repos/<repo>/pulls?head=<owner>:<branch>&state=open"`. If there is one, pushing updates it. Otherwise create it with `gh api repos/<repo>/pulls -f title=... -f head=<branch> -f base=<base> -f body=...`. The PR body has:
   - a one-line summary and the Linear ticket link;
   - a table of acceptance criteria → evidence (test name or file).
   - the domain docs that the PR adds or changes, if any.
7. **Wait for CI** in a subagent. It polls `gh api repos/<repo>/commits/<head sha>/check-runs` about every 30 seconds until the required check has completed. If the check failed, the subagent reads the job log with `gh api repos/<repo>/actions/jobs/<job id>/logs` and returns the error. Fix and push. That counts as a failed attempt.
8. Comment `🤖 build: success — PR <url>` on the ticket. Tell the human in chat in one line, with the PR link.

## Done when

The PR is open, the required check is green on its latest commit, and every acceptance criterion has evidence.

## Escalation

After 3 failed attempts (verify or CI), follow Retries in `CLAUDE.md`.

## Next

Continue with `factory-review`.
