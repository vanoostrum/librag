---
name: factory-spec
description: Factory step 1. Turn a feature description or a Linear ticket into a spec with testable acceptance criteria, then stop at the spec gate. Use when the human asks to work on a ticket or describes a new feature.
model: opus
argument-hint: "<ticket key or feature> [design-variants=<n>] [platforms=<list>] [note=<text, file, or link>]..."
---

# factory-spec

Read the factory config and rules in `CLAUDE.md` first. Then load the `bstack` skill with the Skill tool, before any pstack skill.

## Input

One of:
- a ticket key, e.g. `LIBRAG-12`;
- a feature description typed by the human.

Optional steering arguments follow it, as Steering in `CLAUDE.md` describes.

## Steps

1. **Get the ticket.**
   - Ticket key: read it, with all comments.
   - Description: create a ticket in the Linear team from the config, with a short title and the description. Tell the human the key.
   - Steering arguments: write them under `## Steering` in the ticket description. They replace the values that are already there.
2. Move the ticket to **Specifying**.
3. **Grill.** Run the `grill-with-docs` skill on the ticket. It asks the human questions in rounds and reads the code to find facts. Follow it, with these factory rules:
   - Read `GLOSSARY.md` and `docs/adr/` first, if they exist.
   - If the ticket came from a plan, read the plan ticket's `## Plan` first. Ask only what the plan left open.
   - Ask the rounds in chat. This is an exception to the Chat rule in `CLAUDE.md`.
   - If the ticket is already clear, the first frontier can be empty. Then skip to the next step.
   - Do not write `GLOSSARY.md` or ADR files in the repo now. Write the new and changed glossary terms and ADRs into the spec, under **Domain docs**. `factory-build` commits them.
   - If the human gave spec feedback, grill only the decisions that the feedback opens again.
   - Read the ticket's `🤖 replan` comments. They name the decisions of other tickets that changed this one.
   - If `factory-build` sent the ticket back with a stale spec, grill only the decisions that the merged code changed.
   - In the last round, ask the human to confirm the test seam: "Test through `<route>` with `TestClient`?" Name any unit test you propose and why.
4. **Design.** If the ticket has the `ui` label, run the `factory-design` skill in ticket mode. It returns the gallery pages for this ticket. If the grill shows that a ticket without the label changes a screen, add the label and run it too.
5. **Write the spec** into the ticket description, below the original text, under `## Spec`. Use the `clear-technical-prose` skill for its text. Base it on the decisions and the code from the grill. Read more code if a plan task needs it.
   - **Goal:** one or two sentences.
   - **Scope:** what changes.
   - **Out of scope:** what does not.
   - **Decisions:** the decisions from the grill, one line each.
   - **Acceptance criteria:** a numbered list. Each one is testable and observable, e.g. "GET /version returns 200 with `{"version": "<pyproject version>"}`". For a `ui` ticket, each screen state cites its gallery page, e.g. "GET /search with no results matches `design/pages/search/empty.html`".
   - **Gallery pages:** for a `ui` ticket only. Each page from `factory-design`, with one line on what it shows.
   - **Testing decisions:**
     - **Test seam:** where the tests connect to the code, normally the HTTP route through `TestClient`. Follow the test seam rule in `CLAUDE.md`. Name any unit test and the reason for it.
     - **What the tests check:** the behavior a client sees, such as status, headers, and body. Not the internals, so the tests stay valid when the code behind the route changes.
     - **Prior art:** the existing tests to copy, e.g. `test_version` in `tests/integration/test_routes.py`.
   - **Plan:** a few ordered tasks, each small enough to test on its own.
   - **Domain docs:** only if there are any. The exact `GLOSSARY.md` entries and ADR files to add or change, in the formats of the `domain-modeling` skill.
   - **Risks:** only if there are any.
   If a spec already exists and the human gave feedback, update it instead and note what changed.
6. **Replan check.** Run the replan check from `factory-next` with this spec's decisions and domain docs.
7. **Gate.** Post `🤖 Gate: spec` with the acceptance criteria, the replan proposals, and "Reply approve, or give feedback." For a `ui` ticket, the gate also approves the gallery pages: list them, and point to their screenshots on the ticket. In chat, ask for approval with the ticket link and the number of criteria. Stop.

## Done when

The ticket has a `## Spec` section and a `🤖 Gate: spec` comment, and the human has been asked. A `ui` ticket also has its gallery pages committed on its branch.

## After approval

See Gates in `CLAUDE.md`. One approval covers the spec and the replan proposals.

1. Apply the replan proposals, as the replan check in `factory-next` describes.
2. Move the ticket to **Ready to build**. Comment `🤖 spec: success — <n> criteria`.
3. Run `factory-next`. It starts the build lane if this ticket or another one is ready, and picks the next grill.
