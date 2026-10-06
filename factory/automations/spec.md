# spec

- Stage: `spec`
- Model class: `reasoning`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: Linear status changed to Specifying, team LibRag; resolve the actual team ID.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: Linear read/write/comment, threaded Send to Slack, Read Slack, PR creation/query.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/write-spec/SKILL.md` for this Linear issue after applying `factory/event-contract.md` and the current readiness boundary.
