# spec-reviewer

- Stage: `review`
- Model class: `review-different-family`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: GitHub Factory Contracts CI completed successfully on a factory PR; exclude spec branches/PRs. The skill independently checks kind, complete required checks and current SHA.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: PR comments/query/checks, Linear read/write/comment, threaded Send to Slack.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/review-against-spec/SKILL.md` for this event after applying `factory/event-contract.md`; return noop for spec PRs, stale SHA or incomplete required checks.
