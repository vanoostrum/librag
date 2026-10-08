# LibRag factory setup — execute in Cursor

You are the Cursor agent configuring the **agnostic software factory** in `vanoostrum/librag`, locally at `~/projects/vanoostrum/librag`. Execute step 1 below. Reuse the existing `docs/`, `factory/`, `.agents/skills/factory/`, and `AGENTS.md`; they have already been copied and adapted. Read them, populate real bindings, and make focused corrections. Do not regenerate these assets from scratch or read credentials from the old project's files.

## Fixed scope and sequence

1. **Now:** configure Linear, Slack, GitHub protections and Cursor automations; prove the generic factory using a docs-only task with both human gates.
2. **Later, separately authorized:** initialize the Python/FastAPI project from the human's existing architecture and project plan. Do not design the product in this setup. The human will run Docker locally.
3. **Later, separately authorized:** add actual build/lint/test commands, project CI and verified project skills, then enable application implementation.

No publishing, deployments, image pushes, release workflow, hosting selection, release secrets or release adapter. `Done` currently means human-approved implementation merged and reported. Shipping is disabled. Do not start steps 2 or 3 to make a factory smoke test easier.

## Inputs already supplied

| Input | Value |
|---|---|
| Repo | `vanoostrum/librag`, default branch `main` |
| Execution harness | Cursor cloud agents and automations |
| Linear | New dedicated team **LibRag**, proposed key **LIBRAG** |
| Slack channels | **librag** (requests/gates), **librag-log** (details) |
| Slack workspace | `clearblocks` from source setup; verify the connected workspace before writing |
| Future stack | Python/FastAPI, with local Docker operated by the human |
| Prepared branch | `codex/factory-setup`; inspect current checkout before creating another branch |

Ask only for missing workspace/account access, approver identity, unavailable team key or capability decisions. Do not ask for Apple accounts, app identifiers, hosting, Docker design, architecture, Python tooling choices, or a product feature plan.

## Working rules

- Work autonomously within this scope. First read this prompt, `AGENTS.md`, `factory/config.yaml`, `factory/linear.yaml`, `factory/stages.yaml`, the automation README, and `docs/adr/`. Continue the existing `SETUP_LOG.md`; do not overwrite it or mark live resources verified merely because files exist.
- Before creating a team/channel/app/automation/label/post, query for an exact match. A dedicated LibRag team is required: do not rename/reuse another project's team. If a previous run already created LibRag, reuse that dedicated team. Keep unused default states; never delete or repurpose another project's resources.
- Check current official docs before API/UI changes. Prefer available authenticated connectors/MCP, verified APIs, and Cursor `/automate` over manual work. A historical 404 does not establish current API availability. Never invent undocumented endpoints or claim capabilities without probes.
- Keep secrets out of chat/logs/Git. Prefer existing scoped OAuth/MCP connections; if keys are necessary, use a dedicated external secret file such as `~/.config/librag-factory/.env` with mode 600 and tell the human exactly which variable to set. Never copy the source project's env file. Commit only IDs/URLs/names and secret names.
- Keep changes on the setup branch and open/update a reviewable setup PR. Do not push to `main`, bypass protection, or merge without the human's explicit gate. Existing source docs and architecture handoffs stay intact except targeted factory adaptations.
- Runtime stages follow the runtime rules in `AGENTS.md`. Prove shared event receipts/serialization before activating overlapping mutating handlers. If Cursor cannot enforce them, configure a minimal shared guard adapter, verify its atomic operations, and record it; do not call a Linear comment, memory, or an agent-local lock an atomic guard.
- Preserve stack neutrality in factory contracts. Instance bindings and Cursor setup may name this repo/team/channels; framework commands belong in future project skills.

### Manual step protocol

Do every accessible part first. Batch missing OAuth/token/account operations when possible. Stop only for a real access/consent/account/capability decision or a required human gate. Present a concrete reviewable action, not a generic permission request:

```text
MANUAL STEP: <short title>
Why: <specific missing capability or required human gate>
Do this: <exact URL and steps checked against current docs>
Then give me: <non-secret ID or just reply done>
Secrets: <external file/variable, or none>
I will verify: <specific read/probe>
```

## A. Preflight and asset validation

1. Inspect git status/remote/branch. Preserve unrelated changes. Reuse the prepared setup branch and existing assets; record source revision from the setup log.
2. Inspect available Slack, Linear, GitHub and Cursor connections. Verify GitHub can access `vanoostrum/librag`, selected Slack workspace identity, and Linear workspace access. Identify the human's Slack user ID for gate approvals, using the authenticated identity if unambiguous.
3. Validate local factory assets in an isolated environment using `factory/requirements.txt`, `factory/scripts/validate_factory.py` and `python3 -m unittest discover -s factory/tests -v`. This validates factory contracts, not application code. No FastAPI app, Dockerfile or project manifest is needed.
4. Inspect current Cursor docs/capabilities, available models and supported automation creation paths. Do not reuse historical model IDs. Choose classes reasoning/coding/fast; reviewer must use a different vendor than the builder. Record model IDs/vendors in config.

## B. Linear — new dedicated LibRag team

1. Query for a dedicated team named LibRag. Create it if absent, with key LIBRAG if available; if the key is occupied by another team, ask for the alternate key rather than hijacking that team. Save the actual key and ID in `factory/linear.yaml`.
2. Reuse/rename defaults only inside LibRag; create missing states:

| State | Linear type | Meaning |
|---|---|---|
| Triage | backlog | Intake/clarification or queued for later project readiness |
| Building | started | Approved factory/docs implementation now; application work later |
| Verifying | started | Generic contract CI now; project CI later |
| Reviewing | started | Independent implementation review |
| Ready to merge | started | Gate 2, human merge approval |
| Done | completed | Confirmed approved implementation merge and completion report |
| Needs human | started | Access/decision/cap failure |
| Canceled | canceled | Canceled item |

Do not add Shipping for this scope. Retain unused default states and record them rather than deleting them.
3. Create/reuse labels `type:feature`, `type:bug`, `type:chore`, `risk:low`, `risk:high`, `factory`, `needs-project-setup`. Distinguish team/workspace label scope and reuse the correct labels idempotently.
4. Populate state/label IDs and verify by querying them back. Do not retain any source project's IDs.

## C. Slack — #librag and #librag-log

1. Query exact channel names in the verified workspace; create missing public channels. Prefer existing authorized tools. Only if a setup bot is needed, reuse `factory/slack-app-manifest.yaml`, inspect an existing installation first, and request one batched OAuth/install step.
2. Save channel IDs in `factory/config.yaml`. Join/invite the necessary setup bot and Cursor app. Ensure another project's intake automations cannot consume Librag requests.
3. Idempotently post and pin guidance: start a work item in #librag; discuss it in its thread; react on the current gate message or reply explicitly to it to approve; ask status any time; only approved people can merge; application work is queued until later steps; Done means merged, with no publishing. Record message timestamps and check pins/history before reposting.
4. Set #librag-log purpose for diagnostics. No top-level request processing occurs there.

## D. Runtime capabilities and guard mechanisms

1. Configure Cursor GitHub/Slack/Linear integrations and repo Linux environment. Use Linear editing tools or `https://mcp.linear.app/mcp` if necessary. Verify that the build trigger fires on a status change to Building.
2. Probe threaded Slack send/read in a designated setup thread, Linear comments/transitions in a setup issue, PR/query/merge permissions under GitHub protection, and reading the existing skills from `main`. Do not assume PR creation includes merge or channel-send includes thread-send. Add the least necessary verified tool/MCP/API capability when missing.
3. Resolve the human Slack approver IDs and store them. Verify gate records bind issue/PR/head/spec/message and reject old approvals.
4. Verify a shared atomic run-claim and durable receipt mechanism for all handlers. Record mechanism and evidence in config. If the harness offers no sufficient mechanism, implement/configure the smallest shared adapter for guard state only; test parallel claims and duplicate delivery. If access or hosting for that adapter is unavailable, report that concrete blocker and leave mutating automations disabled. Do not introduce the application scaffold or publishing to solve it.
5. Keep automatic Bugbot Autofix/other competing fixers off until a single owner per feedback cycle is enforced. Independent read/review tools may be used without replacing either human gate. Inspect spend settings and ask only if a budget decision is actually needed.

## E. GitHub bootstrap and protection

1. Reuse `.github/workflows/factory-contracts.yml` and PR template. Mirror relevant issue labels in GitHub. The only current required check is `Factory Contracts`, which runs on every PR without path filtering; there is no app build/lint/test/release pipeline yet.
2. Update configured real bindings and log evidence, validate assets, commit on the setup branch and open/update a setup PR. Wait for the human to review and approve its merge. Ensure no automation is active until the repo-backed skills/config are on `main`.
3. After the approved merge, enable PR-required protection on main, require Factory Contracts, prohibit force pushes, and avoid bypass permissions for the factory. Verify merge tooling respects it. Do not require future project checks that do not exist yet. Any settings blocked by account access require a specific manual step.

## F. Cursor automations — reuse checked-in definitions

1. Derive bindings from `factory/stages.yaml` and `factory/automations/README.md`; use the real repo/team/channel IDs, current models and configured tools. Keep prompts one line pointing to the existing skill.
2. Create/update **disabled** automations: front-desk message/reaction (split only if needed), build (factory/docs mode), ci-fixer, spec-reviewer, comment-fixer, merge-completed. Do not create release-notes or publishing automation. Document IDs/URLs/triggers/tools/filters in SETUP_LOG.
3. Prefer Cursor `/automate` or a currently supported API/provider if available. If the agent cannot configure an automation, provide concrete field values derived from the file and one batched manual setup step; never ask the human to reconstruct the definitions.
4. Enforce implementation-only filters for review/comment-fix/completion and full skill guards even when filters are limited. For CI, query all configured required checks for the current PR head. Account for early CI/merge events by reconciling live state after a transition.
5. Run `validate_factory.py --runtime` after filling bindings/models/probes. Activate stage handlers, completion and front desk last. Set `runtime.activated` only after verification. A missing receipt/serialization or merge/thread capability blocks activation, not asset preparation.

## G. Factory-only smoke test

Ask the human to post in #librag: **“Document the factory handoff: application setup is step 2, build/lint/test adapters are step 3, and publishing is out of scope. Add the short guide at docs/factory-handoff.md.”**

Watch: one LibRag issue → questions in the thread → spec in Linear → human approval → docs implementation PR → Factory Contracts → independent AC/evidence review → Gate 2 → human approval → confirmed implementation merge → completion thread → Done.

Also verify and record: status creates no issue; clarification resumes one intake; repeated delivery produces no duplicate side effects; old approvals/current-head mismatches are ignored; one writer owns a feedback cycle; failures count without commits; the fourth repair never starts; missing/failed contract checks block merges; completion retries do not merge/post twice; an application feature request remains Triage at readiness 1. Use controlled docs/config failures and restore them on branches, never weaken main protection.

Do not use a health/version endpoint, Docker build, real book data or product feature as the smoke test. No application setup or publishing belongs in this exercise.

## H. Wrap-up and stop

Update SETUP_LOG with resource links, actual configuration, verified probes and smoke evidence. Commit final runtime changes through a human-reviewed PR if necessary. Report what is active, what remains blocked/unverified and how to send work in #librag. Keep readiness at 1, application implementation false, publishing false. Stop after generic factory setup; steps 2 and 3 await separate instructions and the existing architecture/plan.

## Official references — recheck during execution

- Cursor automations: https://cursor.com/docs/cloud-agent/automations
- Cursor skills: https://cursor.com/docs/skills
- Cursor cloud agents: https://cursor.com/docs/cloud-agent
- Linear API: https://linear.app/developers/graphql
- Linear MCP: https://linear.app/docs/mcp
- Slack methods/manifests: https://docs.slack.dev/reference/methods/ · https://docs.slack.dev/reference/app-manifest/
- GitHub protection: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- GitHub CLI: https://cli.github.com/manual/
