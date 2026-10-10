# Cursor automations

All automations target repository `vanoostrum/librag` on branch `main`, use a Linux cloud environment, and have memory off. Models come from `factory/config.yaml`; the reviewer and the builder use different vendors. The live definitions are in Terraform at `~/.config/librag-factory/automations/automations.tf`, with IDs in `SETUP_LOG.md`.

Each prompt is one line: `Run .agents/skills/factory/<skill>/SKILL.md for this event.` `AGENTS.md` carries the shared rules.

| Automation | Trigger | Skill | Model class | Tools |
|---|---|---|---|---|
| librag-front-desk | Slack message in #librag (regex `.+`, so thread replies count) and ✅ reaction in #librag | front-desk | reasoning | Read Slack, Send Slack, Linear, GitHub merge |
| librag-build | Linear status changed to Building, LibRag team | implement-task | coding | Send Slack, Linear, branch push |
| librag-ci-fixer | GitHub CI completed with failure, `vanoostrum/librag` | fix-ci-failure | coding | Send Slack, Linear, branch push |
| librag-spec-reviewer | GitHub CI completed with success, `vanoostrum/librag` | review-against-spec | review-different-family | PR comments, Send Slack, Linear |
| librag-comment-fixer | PR comment, `vanoostrum/librag` | implement-task (review feedback mode) | coding | PR comments, Send Slack, Linear, branch push |
| librag-merge-completed | PR merged into `main`, `vanoostrum/librag` | write-release-notes | fast | Send Slack, Linear |

No automation gets Cursor's PR creation tool (`open_git_pr`). It opens PRs as the Cursor app and as drafts. `pr.py upsert` opens them as `chef-willie[bot]` and ready for review. Every automation that pushes or opens a PR needs the `GITHUB_APP_PRIVATE_KEY` secret. Without it, `upsert` fails.

"Linear" is the personal Linear MCP server (`https://mcp.linear.app/mcp`), attached by name. Linear triggers depend on the Cursor Linear app being a member of the LibRag team. There is no publishing automation.

The provider has no branch filter, so each skill ignores PRs that do not come from a `<key>-<num>/<slug>` branch. Keep automations disabled until this setup is on `main`, branch protection is applied, and an approver is configured. Turn on front desk last.
