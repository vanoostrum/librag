---
name: write-release-notes
description: Report a confirmed, approved implementation merge in its Slack thread and move the issue to Done. Publishing is disabled.
---

# write-release-notes

1. Run only in merge-completion mode for a merged PR from a factory issue branch. Ignore anything else.
2. Confirm that the merged head matches the latest merge gate and spec revision. Escalate an unapproved merge instead of closing it.
3. Post once: `<KEY>-<num> merged: <PR URL> (<merge SHA>). <what changed and how to inspect it>`. On a retry, check for an earlier post first.
4. Move only this issue to Done. Never merge again, and never claim publishing or local execution.
