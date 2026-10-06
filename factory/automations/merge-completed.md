# merge-completed

- Stage: `merge-completed`
- Model class: `fast`; actual ID/vendor from `factory/config.yaml`.
- Repository: `vanoostrum/librag`, default context `main`; query/use the event PR head branch for mutations.
- Trigger: GitHub pull request merged into main, repository vanoostrum/librag; implementation PRs only. Exclude spec/setup/untracked PRs.
- Branch filter: `<key>-*`, lowercase actual `factory/linear.yaml` key; exclude `*-spec` for implementation-only handlers. Skill guards remain required if UI filtering is limited.
- Tools: GitHub PR/commit query, Linear read/write/comment, threaded Send to Slack.
- State, receipts, ownership and approval guards: `factory/event-contract.md`.
- Activation: disabled until setup probes pass. Record automation ID/URL and settings in `SETUP_LOG.md`.
- Prompt (one line):

> Run `.agents/skills/factory/write-release-notes/SKILL.md` in merge-completion mode for this merged implementation PR after applying `factory/event-contract.md`; no publishing or local execution is performed.
