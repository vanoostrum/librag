---
name: fix-ci-failure
description: Fix a failed required check on the current head of a factory PR without weakening the check.
---

# fix-ci-failure

1. Ignore runs on `main`, stale heads, closed PRs, and unrelated branches.
2. Read the first real error, for example with `gh run view <id> --log-failed`.
3. For factory failures, run `factory/scripts/validate_factory.py` and the unit tests. For application failures, use the project verify skill. Never guess commands.
4. Rerun a flaky or infrastructure failure once. Otherwise fix the cause. Do not disable checks or tests.
5. Push the fix with `ci-fix` trailers and leave the issue in Verifying.
