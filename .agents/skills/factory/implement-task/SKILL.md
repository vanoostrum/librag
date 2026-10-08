---
name: implement-task
description: Implement the approved spec from the Linear issue and open or update its pull request. Also fixes an owned round of review feedback.
---

# implement-task

The input is an issue in Building with an approved `## Spec (rev N)` in its description. `python3 factory/scripts/spec.py show --description <file>` prints the revision and the spec.

1. Run `python3 factory/scripts/pr.py branch --issue <KEY-num> --title "<issue title>"`. On a retry it checks out the existing branch.
2. Implement against the acceptance criteria. Decide small details yourself. If a criterion cannot be met or contradicts the codebase, ask in the thread and move the issue to Needs human. Do not change the scope yourself.
3. Prove each criterion. Use tests for runtime behavior and a file or config check for documentation and configuration. Run the factory validation.
4. Commit with `python3 factory/scripts/pr.py commit --issue <KEY-num> --stage build -m "<message>"`. Use stage `comment-fix` in review feedback mode.
5. Write the evidence as JSON (`[{"ac": "1. ...", "evidence": "..."}]`). Run `python3 factory/scripts/pr.py upsert --issue <KEY-num> --title "<title>" --rev <N> --issue-url <url> --thread <permalink> --evidence <file>`. It prints the PR URL and head SHA. Move the issue to Verifying.

**Review feedback mode:** address only the findings this run owns. Reply once per finding, then move the issue to Verifying.
