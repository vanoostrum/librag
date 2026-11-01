---
name: factory-next
description: Factory picker. Pick the next Linear ticket for the spec lane and the build lane, and start both lanes in parallel. Also holds the replan check and the milestone checkpoint. Use after a plan gate, a spec gate, or a merge, or when the human asks the factory to pick up the next ticket.
model: haiku
---

# factory-next

Read the factory config and rules in `CLAUDE.md` first.

The factory works in two lanes. The **spec lane** needs the human: grill, design, and the spec gate. The **build lane** runs on its own: build, test, review, up to the merge gate. This skill picks the next ticket for each lane and starts the lanes in parallel, so the human answers grills while earlier tickets build.

## Input

None, or a Linear project. Without a project, use every open ticket in the Linear team from the config.

## Lanes

| Lane | Takes a ticket when | Limit | Runs |
|---|---|---|---|
| Spec | It is in **Todo**, and each ticket that blocks it is in **Ready to build**, **Building**, **In Review**, or **Done**. | One ticket in **Specifying**, and at most 4 tickets in **Ready to build**. | `factory-spec`, in this session. |
| Build | It is in **Ready to build**, and each ticket that blocks it is **Done**. | One ticket in **Building**. A ticket in **In Review** does not count. | `factory-build`, then `factory-review`, in a new session. |

"Blocks" means a Linear "blocked by" relation. A blocked ticket is never picked. A ticket can be grilled before its blockers are built, because the grill needs their decisions, not their code.

## Steps

1. **Read the board.** List the open tickets with their state, priority, and blocking relations. Skip tickets in **Needs human** and plan tickets.
2. **Sort** the candidates of each lane by Linear priority, then by the build order in the plan ticket's `## Plan` table.
3. **Build lane.** If the lane has room and a ticket is ready, start a new Claude Code session for it with this prompt: `Run factory-build on <key>, then factory-review. Stop at the merge gate.` Use what the environment offers. In a claude.ai project, ask the coordinator for a new thread. In a terminal, run `claude -p "<prompt>"` in a background shell. A build must not run in this session, because the grill in this session waits on the human.
4. **Spec lane.** If the lane has room and a ticket is ready, tell the human in chat in one line that a grill is waiting, with the ticket link. Then run `factory-spec` on it in this session.
5. **Nothing to pick.** If neither lane can take a ticket, say why in one line: what each lane waits on.

## Replan check

`factory-spec` runs this after the human approves a spec. `factory-merge` runs it after a merge. It keeps the backlog in step with what the factory has learned.

1. Read what is new: the decisions and domain docs of the approved spec, or the glossary terms, ADRs, and code of the merged PR.
2. Read the open tickets in the same Linear project, with their goals and gallery pages.
3. For each ticket that the new facts affect, propose one change: rewrite the goal, split, drop, add a ticket, change a blocker, or reorder. Do not propose details that the ticket's own grill will settle.
4. **Gallery pages.** For each open `ui` ticket, check its gallery pages against the new facts:
   - A change to the look lives in `design/gallery.css` or, from gallery stage 2, `design/components/`. Every page follows. Propose no redraw. Name the pages to look at again in their next screenshots.
   - A change to a screen, such as a field, a state, or the copy, does not follow on its own. Propose to mark the page stale. Do not redraw it now: `factory-design` redraws it when that ticket is grilled.
5. Post the proposals with the gate or the merge message, as the calling step says. They need the human's approval. One approval covers the gate and the proposals.
6. **After approval**, apply each change in Linear. Mark a stale page with a ticket comment `🤖 replan: stale <page> — <the decision that changed it>`. A change to a ticket in **Ready to build** moves it back to **Todo**, so the spec lane grills it again.
7. Comment on each changed ticket `🤖 replan: success — <one line>`.

If nothing is affected, say "No replan changes" in the gate or merge message.

## Milestone checkpoint

`factory-merge` runs this when the merged ticket was the last open ticket of a Linear milestone.

1. Post on the plan ticket, and tell the human in chat: what shipped in the milestone, with links to the PRs and the app screenshots, and the decisions made.
2. Ask the human to reorder the priorities in Linear if needed. For a bigger change of direction, offer `factory-plan` for the next increment.
3. Run the Steps above only after the human replies.

## Done when

Each lane has a ticket, or the human knows what each lane waits on.
