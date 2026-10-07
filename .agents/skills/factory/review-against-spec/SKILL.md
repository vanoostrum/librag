---
name: review-against-spec
description: Review an implementation PR against the approved Linear spec once every required check is green on its current head, then post the merge gate or one round of findings.
---

# review-against-spec

Run on a model from a different vendor than the builder.

1. Stop unless the issue is in Verifying or Reviewing, the event belongs to the current PR head, and every required check is green. Move the issue to Reviewing.
2. Check every acceptance criterion against the latest diff, including criteria earlier commits had already met. Runtime criteria need tests. Also check the out-of-scope list and the security implications.
3. Post one review with an `AC | met? | evidence` table and labeled findings.
4. **Blocking findings:** start a new feedback round, assign it to Building, and move the issue there. Do not also leave it for comment-fix.
5. **No blocking findings:** set Ready to merge. Post the merge gate in the thread with the PR URL, head SHA, and spec revision. Add a Linear comment `Gate: merge, head <sha>, spec rev N, message <ts>`.
