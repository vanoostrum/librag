# comment-fixer

- Stage: `comment-fix`
- Model class: `coding`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: GitHub PR review comment or review submitted with changes requested; implementation factory PRs only. Claim an actionable feedback cycle not already owned by Building/ci-fix.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: PR query/comments/branch push, Linear read/write/comment, threaded Send to Slack.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/implement-task/SKILL.md` in review-comments mode only for a claimed unowned actionable cycle after applying `factory/event-contract.md`; otherwise return noop.
