---
name: factory-plan
description: Factory step 0. Turn a project spec, or a set of features for a working app, into an approved plan of Linear tickets and a rough gallery, then stop at the plan gate. Use for new work that spans more than one or two tickets or adds a new user flow.
model: opus
---

# factory-plan

Read the factory config and rules in `CLAUDE.md` first. Then load the `bstack` skill with the Skill tool, before any pstack skill.

This step works at a helicopter view. It decides how the work is broken up and what the main screens look like. The details of each ticket wait for `factory-spec` and `factory-design` in ticket mode.

## When to use it

- A new project starts from a spec.
- A working app gets a set of new features, for example after the MVP.

A feature that fits in one or two tickets skips this step and starts at `factory-spec`.

## Input

A project spec or a feature description from the human, as text, a file, or a link.

## Steps

1. **Plan ticket.** Create a Linear project for this plan, or for this increment of an existing app. Create a plan ticket in it, titled `Plan: <name>`, with the input in its description. Move it to **In Progress**. Tell the human the key. Gate comments and the plan go on this ticket.
2. **Read what exists.** For an increment, read the code, `GLOSSARY.md`, `docs/adr/`, `design/`, and the open tickets in the Linear team first. For a new project, read whatever the repo already has.
3. **Helicopter grill.** Run the `grill-with-docs` skill with the factory rules from `factory-spec`, with these changes:
   - Keep the frontier coarse: users, main flows, boundaries, out of scope, big risks, and constraints. Leave exact states, edge cases, and copy to the grill of each ticket.
   - For an increment, ask only about the new scope and its effect on the existing app: migrations, flows that change, and what must keep working.
   - Write the glossary terms and ADRs directly to `GLOSSARY.md` and `docs/adr/` in step 6. They are the decisions every ticket of the plan shares.
4. **Slice the work** into vertical tickets. Each ticket delivers something a client can see and test on its own. Give each one a title, a goal of one or two sentences, and its dependencies. Give the `ui` label to each ticket that adds or changes a screen. Put the tickets in build order.
5. **Design pass.** If any ticket has the `ui` label, run `factory-design` in project mode with the main flows. It sets the visual identity if there is none, and draws one rough page per main flow. For an increment, it extends the existing gallery and lists each existing page that changes. Add a ticket for each missing screen that it finds, and repeat this step for the new flows.
6. **Commit** the domain docs to the plan ticket's branch, next to the gallery commits from step 5, with the `Factory-Issue` trailer. Open a PR against the base branch, as `factory-build` step 7 describes. Its body has the plan.
7. **Write the plan** into the plan ticket description, under `## Plan`, with the `clear-technical-prose` skill:
   - **Goal:** one or two sentences.
   - **Scope** and **Out of scope.**
   - **Decisions:** the decisions from the grill, one line each.
   - **Tickets:** a table in build order, with title, goal, `ui` yes or no, depends on, and gallery pages.
   - **Changed pages:** for an increment, each existing gallery page that changes, and how.
   - **Risks:** only if there are any.
8. **Gate.** Post `🤖 Gate: plan` with the ticket table, the gallery screenshots, and the PR link, and "Reply approve, or give feedback." In chat, ask for approval with the ticket link and the number of tickets. Stop.

## After approval

1. Wait for the required check on the PR to be green, as `factory-build` step 8 describes. The plan gate approval is also the merge approval for this PR. Merge it with steps 2 to 4 of `factory-merge`. No commits may have been pushed after the `🤖 Gate: plan` comment; if there were, ask for approval again.
2. Create each ticket from the table in the Linear project. Each ticket gets its goal, the decisions it depends on, links to its gallery pages, the `ui` label where set, and blocking relations for its dependencies. Create the `ui` label in the team if it does not exist.
3. Move the plan ticket to **Done**. Comment `🤖 plan: success — <n> tickets in <project link>`. Tell the human in chat in one line.

## Next

Each ticket starts at `factory-spec`, in build order. Its grill reads the plan's decisions first and asks only what the plan left open.
