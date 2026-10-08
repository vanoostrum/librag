# LibRag factory setup log

Runbook: `docs/factory-setup-prompt.md`. Source: `vanoostrum/nap-time`, revision `3bcafe6bb97db862762073beea49e19e2661f28c`.
Prepared files are not evidence of live runtime configuration. Record IDs/URLs/names and verification, never secrets.

## Prepared repository assets

- [x] Copied and adapted docs, factory definitions, AGENTS.md and all eight factory skills.
- [x] Removed inherited team/state/channel bindings and historical model mapping.
- [x] Defined factory-first readiness, two human gates, merged-and-reported completion, no publishing.
- [x] Added generic contract validation and guard policy tests.

Preparation validation: factory assets pass static validation; all eight skills pass the skill frontmatter validator; 38 unit tests pass locally. Live integration and GitHub Actions execution remain unverified until Cursor executes the runbook.

## Cursor execution checklist — step 1 only

- [x] A. Read assets, inspect current GitHub/Slack/Linear/Cursor connections and verify docs.
- [x] B. Create/select a new dedicated LibRag team; record actual key/team/state/label IDs.
- [x] C. Create/reuse #librag and #librag-log in the selected workspace; record IDs, invite Cursor, pin guidance idempotently. Channels, the pin, and Cursor's membership are recorded below.
- [x] D. Configure named approvers and current available model mapping. Models are recorded. The approver is `U0C4NGQ0QFP` (theo) in `factory/config.yaml`.
- [ ] E. Configure and prove shared receipts/run serialization, threaded replies, Linear writes and protected merges. Receipts, serialization, and thread read are proven. A Linear write through the automation MCP, and protected merge, are not.
- [ ] F. Review/merge setup PR, verify Factory Contracts, apply branch protection without bypassing human gates.
- [x] G. Create disabled automations from existing specs; record IDs/URLs, tool access and filters.
- [ ] H. Validate runtime config, activate handlers then front desk, exercise docs-only happy path and failure/replay boundaries. `runtime.activated` stays false.
- [ ] I. Commit final runtime bindings/evidence and report remaining limits.

## Deferred scope

- Step 2: Initial Python/FastAPI project setup using the human's existing architecture/plan; human runs Docker locally.
- Step 3: Actual build/lint/test adapter and project CI; only then enable application automation.
- Publishing/deployment: excluded.

## Resources and capability evidence

Checked 2026-10-06 against the current Linear GraphQL API, Slack Web API, GitHub REST API, Cursor cloud-agent model list, Cursor automations docs, and Terraform provider `cursor/cursor` 0.7.0.

### Identities

- GitHub repo `vanoostrum/librag`, default branch `main`, viewer `vanoostrum` with admin on the repo. SSH authentication works. The active `GH_TOKEN` can read refs and repository metadata.
- Linear viewer Theo (`theo@clearblocks.nl`), organization url key `nap-time`. The Nap Time team was left unchanged.
- Slack workspace Clearblocks, team `T0C4RLU9EK0`, `https://clearblocks.slack.com/`. Setup bot `factorysetup` (`U0C4MUBPSD9`). Granted scopes: `channels:manage`, `channels:join`, `channels:read`, `chat:write`, `pins:read`, `pins:write`.
- Cursor API key `factory-setup` belongs to `theo@clearblocks.nl`.
- Secrets used for setup live only in `~/.config/librag-factory/.env` (mode 600): `LINEAR_API_KEY`, `SLACK_BOT_TOKEN`, `CURSOR_API_KEY`. They are not in git.

### Linear team LibRag

- Team `71f22498-2676-45e7-ada7-7b9f2fd61c8b`, key `LIBRAG`, name LibRag. Created for this factory. https://linear.app/nap-time/team/LIBRAG
- State and label IDs are in `factory/linear.yaml`. Queried back after create.
- Renamed only inside LibRag: Backlog to Triage, In Progress to Specifying, In Review to Spec review. Created Building, Verifying, Reviewing, Ready to merge, and Needs human. Kept Done and Canceled.
- Unused defaults retained: Todo (`unstarted`), Duplicate (`duplicate`).
- LibRag team labels were created for the seven factory names. Same-named labels on the Nap Time team were not reused. Workspace labels Feature, Bug, and Improvement were left in place.
- Write probe: created LIBRAG-1 in Triage, added comment `b0bfc42d-1029-488a-b09d-71da59752ae5`, moved it to Specifying, then canceled it. Created LIBRAG-2 directly in Specifying and canceled it. https://linear.app/nap-time/issue/LIBRAG-1/factory-setup-probe and https://linear.app/nap-time/issue/LIBRAG-2/factory-setup-probe-created-in-specifying
- Both issue histories were empty. Linear treats property changes in the first three minutes as part of creation and omits them from the activity log. Status automations therefore listen for `status_changed` on the Specifying and Building state IDs, and front desk still creates Triage before transitioning.

### Slack

- `#librag` `C0C824T9C1W`. Pinned guidance `1791317249.418609`. Pins were empty before that post.
- `#librag-log` `C0C79MG62U9`. Purpose: `LibRag factory diagnostics. No top-level request processing.`
- Thread send probe in `#librag-log`: parent `1791317267.787839`, reply `1791317268.028429` with that `thread_ts`.
- Initial probe: `conversations.history` and `conversations.replies` returned `missing_scope` (`channels:history`), and `users.lookupByEmail` returned `missing_scope`. Superseded on 2026-10-08: both history calls succeed, and `approvals.slack_user_ids` is `U0C4NGQ0QFP`. See Deviations.
- The Cursor Slack app has not been invited to either channel.

### Models

From `GET https://api.cursor.com/v0/models` on this date. Builder and reviewer use different vendors.

| Class | ID | Vendor |
|---|---|---|
| reasoning | `claude-opus-5-thinking-high` | anthropic |
| coding | `gpt-5.6-sol-high` | openai |
| review-different-family | `claude-fable-5-thinking-high` | anthropic |
| fast | `gemini-3.7-flash-high` | google |

### Guard ref

`factory/scripts/guard_store.py` stores claims and receipts in `state.json` on `refs/heads/factory-guards`. Updates are fast-forward pushes. Ref tip after the probe: `ffac02b364cad0dd1a5199264659ea9ef5b0f28e`.

- Parallel claims for `probe-issue`: `owner-b` acquired, `owner-a` busy.
- Receipt `probe-delivery`: first record `ok`, second `duplicate`. That probe stored a finished receipt. Current code treats only `success`, `noop`, and `escalated` as finished. `started` and `failed` can be recorded again, and `begin` claims before it writes a receipt.
- In-process races are covered by `factory/tests/test_guard_store.py`. Revision binding is covered by `factory/tests/test_policy.py`.
- The local `GH_TOKEN` cannot create git blobs (`403`). The probe used SSH as `vanoostrum`.

### GitHub protection and labels

- `GET /repos/vanoostrum/librag/rulesets` returned an empty list.
- Creating a ruleset, creating labels, reading classic branch protection, and creating a git blob all returned `403 Resource not accessible by personal access token`.
- Factory labels are not on GitHub yet. Default GitHub labels were left in place.
- No Bugbot Autofix or other competing fixer was enabled. `protected_merge` stays false. `runtime.activated` stays false. Readiness stays 1. Publishing stays false.

### Disabled automations

Created with provider `cursor/cursor` 0.7.0, scope `user`, `enabled=false`, `memory_enabled=false`, `skip_install=true`. No release-notes automation was created. A later plan refreshed all seven and proposed no resource changes.

| Name | ID | URL |
|---|---|---|
| librag-front-desk | `6572b625-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/6572b625-c1c2-11f1-bb68-864e54d14197 |
| librag-build | `6574556a-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/6574556a-c1c2-11f1-bb68-864e54d14197 |
| librag-ci-fixer | `657337b2-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/657337b2-c1c2-11f1-bb68-864e54d14197 |
| librag-spec-reviewer | `6572ba9a-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/6572ba9a-c1c2-11f1-bb68-864e54d14197 |
| librag-comment-fixer | `65757452-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/65757452-c1c2-11f1-bb68-864e54d14197 |
| librag-merge-completed | `65707ebf-c1c2-11f1-bb68-864e54d14197` | https://cursor.com/automations/65707ebf-c1c2-11f1-bb68-864e54d14197 |

Tools: generalized Slack send, Slack read, and PR comments where the stage needs them. Prompts are one line each: run the skill for this event. The Linear trigger is limited to the LibRag team and the Building state. Git triggers are limited to `vanoostrum/librag`. Provider 0.7.0 has no branch-name filter, so skills ignore PRs from branches other than factory issue branches.

2026-10-07 rework (ADR 0002): `librag-spec` (`6572a6f8-…`) was destroyed. Front desk now runs on `claude-opus-5-thinking-high` and handles questioning, the spec in Linear, and spec approval. Prompts no longer mention the event contract. All six automations are still disabled, and a follow-up plan showed no changes. The Linear states Specifying and Spec review still exist but are unused.

## Deviations and fixes

- Provider 0.7.0 has no workflow-run trigger and no separate pull-request review-comment trigger. CI handlers use CI completed (`failure` or `success`). The comment handler uses PR `commented`. Skills still ignore stale runs, unrelated PRs, and unowned comments.
- Generalized Slack send causes Cursor to add a read-Slack action. That action is part of the saved automations.
- The first apply reported a provider consistency error after the server added that read action. All seven automations were still created disabled. The tainted instances were untainted and a refresh plan proposed no resource replacement.
- The first Slack app install could not read threads or look up users, even though `factory/slack-app-manifest.yaml` listed `channels:history`. Reinstalling the scopes fixed both. See the 2026-10-08 note below.
- GitHub administration was blocked by the first token. On 2026-10-08 a new token (admin on the repo, expires 2026-11-05) read labels, rulesets, and Actions permissions, created the seven factory labels, and opened [PR #1](https://github.com/vanoostrum/librag/pull/1), where Factory Contracts passed. Branch protection waits until PR #1 is on `main`.
- On 2026-10-08 the Linear API key read the LibRag team, and the setup bot was a member of #librag and #librag-log. After the scopes were reinstalled, the bot had `channels:history` and `users:read`, `conversations.history` and `conversations.replies` succeeded, and `users.info` confirmed that `U0C4NGQ0QFP` is the human user theo. That ID is the approver. The #librag members are theo, factorysetup (`U0C4MUBPSD9`), and Cursor (`U0C4P52LKDK`). `slack_threads` is true because that thread read succeeded.
- On 2026-10-08 the Cursor Linear app (`1d8f7643-e165-46a6-b76f-5e5654b329da`) was installed in Clearblocks but was a member of only the Nap Time team, not LibRag. At 20:12 the Cursor app was a member of both LIBRAG and NAP.
- On 2026-10-08 a read-only cloud agent probe through the Cursor SDK failed at startup: `The SCM integration does not have access to repository vanoostrum/librag`. The Cursor GitHub App needs access to this repo before any automation can clone it. After theo granted the app access at 20:14, the same probe finished. It listed MCP servers `cursor, cursor-cloud, cursor-subscriptions, Linear, Notion`, found 68 Linear tools, and read every LIBRAG state. All six automations now have the action `mcp = { server = "Linear" }`, which uses theo's OAuth. Linear edits would appear as theo. A follow-up Terraform plan showed no changes, and all six are still disabled. The probe was read-only, so `linear_write` stays false until a write through that MCP is recorded.
- On 2026-10-08 a read-only probe of `gh` in a cloud VM found `gh` 2.102.0, Python 3.12.3, and PyYAML 6.0.1. The VM's `GH_TOKEN` is a git-only placeholder, and the API rejects it with 401. With `GH_TOKEN` unset, `gh` uses the stored `cursor` login, a GitHub App token (`ghs_`), which listed PRs and check runs. `factory/scripts/cli.py` retries `gh` that way when GitHub returns "Bad credentials". Merging through that login is not yet proven; the smoke test will show it.
- On 2026-10-08 front desk got an MCP action `server = "Linear"`. Cursor returned no `server_id`, so it is not verified that the name matches a configured server.
- Smoke test is not started. The approver is configured. Activating handlers before the skills are on `main` and before branch protection would skip the gates.
