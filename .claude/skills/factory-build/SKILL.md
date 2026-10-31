---
name: factory-build
description: Factory step 2. Implement an approved spec with tests first, verify it, and open a pull request. Use after the spec gate is approved, or when CI fails on a factory PR.
model: sonnet
---

# factory-build

Read the factory config and rules in `CLAUDE.md` first. Then load the `bstack` skill with the Skill tool, before any pstack skill.

## Input

A ticket in **Ready to build** whose spec gate is approved.

## Steps

1. **Check that the ticket is ready.**
   - The spec gate must be approved.
   - Each ticket that blocks it must be **Done**.
   - **Stale spec.** Read the glossary terms, ADRs, and code merged since the `🤖 Gate: spec` comment. If they contradict the spec, do not guess. Move the ticket to **Todo**, comment `🤖 build: escalated — stale spec: <what changed>`, and tell the human. The spec lane grills only the decisions that changed.
   - If a check fails for another reason, stop and say so.
   Then move the ticket to **Building**.
2. **Branch.** Create or check out the branch from the naming rule, based on the latest base branch.
3. **Domain docs.** If the spec has **Domain docs**, write them to `GLOSSARY.md` and `docs/adr/` as the spec says. Commit them with the `Factory-Issue` trailer.
4. **Per task in the plan:**
   1. Write a failing test for it, at the test seam from the spec.
   2. Make it pass with the smallest change.
      For a `ui` ticket, build each screen to match its gallery page in the spec, on each platform in `design/README.md`: the same structure, states, copy, and look. Write the app's own styles; do not link `design/gallery.css`. Do not change `design/` in this step, except for a polish fix from the merge gate (see Gates in `CLAUDE.md`).
   3. Run the full verify (see the verify skill from the config) in a subagent on the `verify` model from `.claude/models.md`. Fix until green.
   4. Commit with the `Factory-Issue` trailer.
5. **Check the acceptance criteria.** Each one must be covered by a test, or explain in the PR why it cannot be. Read the coverage report: a new line or branch under `Missing` needs a test or a reason in the PR.
6. **Prove it in the running app** with the app driver skill from the config. Run it in a subagent on the `app driver` model from `.claude/models.md`.
   - If the ticket adds or changes a route, first add or update its file in the skill's feature map.
   - Drive every feature that the ticket adds or changes. Use the recipes in the feature map.
   - Evidence is the response output for every route, and a screenshot for every HTML page.
   - For a `ui` ticket, take the app screenshot and the gallery screenshot of each screen state on each platform in `design/README.md`, with `$V gallery <feature id> <page> <platform>`. The subagent compares each app screenshot with its gallery screenshot. A visible difference in layout, states, copy, or look is a fail.
   - The subagent returns pass or fail, the transcripts, and the paths of the screenshots.
   - A fail counts as a failed attempt. Fix the code and go back to step 4.
   - Attach each screenshot to the Linear ticket. For a `ui` ticket, attach each app screenshot next to its gallery screenshot.
7. **Open the PR** against the base branch. Write the PR body with the `clear-technical-prose` skill. First look for an existing one: `gh api "repos/<repo>/pulls?head=<owner>:<branch>&state=open"`. If there is one, pushing updates it. Otherwise create it with `gh api repos/<repo>/pulls -f title=... -f head=<branch> -f base=<base> -f body=...`. The PR body has:
   - a one-line summary and the Linear ticket link;
   - a table of acceptance criteria → evidence (test name or file, and the app evidence);
   - an **App evidence** section with the transcripts in fenced blocks, and links to the screenshots on the Linear ticket.
   - for a `ui` ticket, a **Gallery** table: screen state and platform → gallery page → app screenshot and gallery screenshot.
   - the domain docs that the PR adds or changes, if any.
8. **Wait for CI** in a subagent on the `CI polling and log reading` model from `.claude/models.md`. It polls `gh api repos/<repo>/commits/<head sha>/check-runs` about every 30 seconds until each required check has completed. If a check failed, the subagent reads the job log with `gh api repos/<repo>/actions/jobs/<job id>/logs` and returns the error. Fix and push. That counts as a failed attempt.
9. Comment `🤖 build: success — PR <url>` on the ticket. Tell the human in chat in one line, with the PR link.

## Done when

The PR is open, each required check is green on its latest commit, every acceptance criterion has evidence, and the PR body has the app evidence.

## Escalation

After 3 failed attempts (verify or CI), follow Retries in `CLAUDE.md`.

## Next

Continue with `factory-review`.
