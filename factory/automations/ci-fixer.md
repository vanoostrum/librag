# ci-fixer

- Stage: `ci-fix`
- Model class: `coding`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: GitHub workflow run completed, failure, Factory Contracts (and explicitly configured future project verification workflows), factory issue branches in vanoostrum/librag.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: GitHub logs/checks/PR query and branch push, Linear read/write/comment, threaded Send to Slack.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/fix-ci-failure/SKILL.md` for this workflow event after applying `factory/event-contract.md`, ignoring stale runs and preserving spec-PR state.
