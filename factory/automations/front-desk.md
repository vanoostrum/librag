# front-desk

- Stage: `front-desk`
- Model class: `fast`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: Slack new message in #librag with regex `.+` to include thread replies; Slack white_check_mark reaction in #librag. Use both triggers, or split message/reaction automations sharing the same receipts/ownership mechanism.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: Read Slack, threaded Send to Slack, Linear read/write/comment, GitHub protected merge/query.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/front-desk/SKILL.md` for this Slack event after applying `factory/event-contract.md` and the current bindings in `factory/config.yaml`.
