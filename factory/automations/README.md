# Cursor automation bindings

Reuse these specifications; do not generate a second factory. Stages are defined in `factory/stages.yaml`, instance values in `factory/config.yaml` and `factory/linear.yaml`, and guards in `factory/event-contract.md`.

## Shared settings

- Repository `vanoostrum/librag`, default branch `main`, Linux cloud environment. Every automation must be repo-backed so it can read the skills; on GitHub events mutate the event's actual PR branch, not `main`.
- Linear triggers select the actual **LibRag** team ID. Slack triggers select the actual **#librag** channel ID; logs go to **#librag-log**.
- Resolve concrete available models during setup. Fill the four model classes in config; reviewer and builder use different vendors. Do not copy historical model IDs.
- Read Slack and send threaded Slack messages where needed. Linear editing/comments via verified native tools or Linear MCP. Protected merges need a verified GitHub merge tool/CLI/API; do not assume “PR creation” includes merging.
- All handlers enforce the shared receipt/ownership/approval contract. Keep automated fix tools from competing for the same feedback cycle.
- Create disabled, then activate only after skills are on `main`, protection and integration probes pass, and runtime configuration is validated. Activate intake last.
- Exact one-line prompts below reference existing skills and the common contract. Cursor can create automations through `/automate`, supported APIs, or UI; verify actual support rather than assuming an endpoint exists.

## Inventory

| Automation | Model class | Current status |
|---|---|---|
| front-desk (message + reaction; split if required) | fast | Configure |
| spec | reasoning | Configure |
| build | coding | Configure, factory/docs mode |
| ci-fixer | coding | Configure |
| spec-reviewer | review-different-family | Configure, implementation PRs only |
| comment-fixer | coding | Configure, owned actionable cycles only |
| merge-completed | fast | Configure, implementation PRs only |
| release-notes | fast | Disabled; do not create/activate |

Official references checked during preparation: [Cursor Automations](https://cursor.com/docs/cloud-agent/automations), [Cursor Skills](https://cursor.com/docs/skills). Recheck them during execution. Threaded Slack replies, protected merges, serialization and duplicate delivery remain runtime probes, not assumed capabilities.
