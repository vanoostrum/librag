# build

- Stage: `build`
- Model class: `coding`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: Linear status changed to Building, team LibRag.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: Linear read/write/comment, threaded Send to Slack, PR creation/query.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/implement-task/SKILL.md` for this issue after applying `factory/event-contract.md`; permit only eligible work at the configured readiness step.
