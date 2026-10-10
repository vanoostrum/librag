---
name: implement-task
description: Implement the approved spec from the Linear issue and open or update its pull request. Also fixes an owned round of review feedback.
---

# implement-task

The input is an issue in Building with an approved `## Spec (rev N)` in its description. `python3 factory/scripts/spec.py show --description <file>` prints the revision and the spec.

1. Run `python3 factory/scripts/pr.py branch --issue <KEY-num> --title "<issue title>"`. On a retry it checks out the one existing branch. If more than one `<key>-<num>/*` branch exists, stop and ask.
2. Implement against the acceptance criteria. Decide small details yourself. If a criterion cannot be met or contradicts the codebase, ask in the thread and move the issue to Needs human. Do not change the scope yourself.
3. Prove each criterion. Use tests for runtime behavior and a file or config check for documentation and configuration. Run the factory validation.
4. Commit with `python3 factory/scripts/pr.py commit --issue <KEY-num> --stage build -m "<message>"`. Use stage `comment-fix` in review feedback mode.
5. Write the evidence as JSON (`[{"ac": "1. ...", "evidence": "..."}]`). Run `python3 factory/scripts/pr.py upsert --issue <KEY-num> --title "<title>" --rev <N> --issue-url <url> --thread <permalink> --evidence <file>`. It prints the PR URL and head SHA. It refuses a branch with no diff against `origin/main`, paths outside the readiness allowlist, or a missing `chef-willie[bot]` token. It marks a draft PR ready. Move the issue to Verifying.
6. Open or update the PR only with `pr.py upsert`. Never use Cursor's PR tool (`open_git_pr`, ManagePullRequest) or any other way to open a PR. PRs are authored by `chef-willie[bot]` and are never drafts. If `upsert` fails, record `failed`, post the error in the thread, and stop. After the retry limit, move the issue to Needs human.

**Review feedback mode:** address only the findings this run owns. Reply once per finding, then move the issue to Verifying.
