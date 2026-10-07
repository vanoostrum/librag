# LibRag factory setup log

Runbook: `docs/factory-setup-prompt.md`. Source: `vanoostrum/nap-time`, revision `3bcafe6bb97db862762073beea49e19e2661f28c`.
Prepared files are not evidence of live runtime configuration. Record IDs/URLs/names and verification, never secrets.

## Prepared repository assets

- [x] Copied and adapted docs, factory definitions, AGENTS.md and all eight factory skills.
- [x] Removed inherited team/state/channel bindings and historical model mapping.
- [x] Defined factory-first readiness, two human gates, merged-and-reported completion, no publishing.
- [x] Added generic contract validation and guard policy tests.

Preparation validation: factory assets pass static validation; all eight skills pass the skill frontmatter validator; ten guard/asset validation tests pass locally. Live integration and GitHub Actions execution remain unverified until Cursor executes the runbook.

## Cursor execution checklist — step 1 only

- [x] A. Read assets, inspect current GitHub/Slack/Linear/Cursor connections and verify docs.
- [x] B. Create/select a new dedicated LibRag team; record actual key/team/state/label IDs.
- [ ] C. Create/reuse #librag and #librag-log in the selected workspace; record IDs, invite Cursor, pin guidance idempotently. Channels and the pin exist. The Cursor Slack app is not invited yet.
- [ ] D. Configure named approvers and current available model mapping. Models are recorded. The approver Slack member ID is not.
- [ ] E. Configure and prove shared receipts/run serialization, threaded replies, Linear writes and protected merges. Receipts, serialization and Linear writes are proven. Thread read and protected merge are not.
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
- `conversations.history` and `conversations.replies` return `missing_scope` (`channels:history`). `users.lookupByEmail` returns `missing_scope`. The approver Slack member ID is still unknown, so `approvals.slack_user_ids` is empty.
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
- Receipt `probe-delivery`: first record `ok`, second `duplicate`.
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
- Slack thread read and the approver lookup need scopes the installed setup bot does not have, even though `factory/slack-app-manifest.yaml` lists `channels:history`.
- GitHub administration is blocked by the current token, so labels and branch protection are not applied. Protection waits until this setup PR is on `main` anyway.
- Smoke test is not started. Activating handlers before the skills are on `main`, before protection, and before a named approver would skip the gates.
