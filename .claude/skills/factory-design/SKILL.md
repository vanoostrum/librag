---
name: factory-design
description: Factory design step. Settle how screens look with the human in Claude Design, then freeze the result into the gallery in design/. Project mode runs from factory-plan; ticket mode runs from factory-spec for tickets with the ui label.
model: opus
---

# factory-design

Read the factory config and rules in `CLAUDE.md` first. Then load the `bstack` skill with the Skill tool, before any pstack skill. Read `design/README.md`: it holds the gallery layout, its rules, and the rollout stages.

The goal is to settle the look once, before the build. The human changes their mind here, on a surface that costs nothing to change. After the gate, the build follows the gallery literally.

## Input

One of:

- **Project mode:** called by `factory-plan`, with the plan's flows and the plan ticket key.
- **Ticket mode:** called by `factory-spec`, with a ticket that has the `ui` label, after the grill.

## Steps

1. **Settle the platforms.** Read `Platforms` in `design/README.md`. If `platforms` under `## Steering` differs from it, use the steering value. If it is `not set`, derive it from the project information, as the Platforms section of `design/README.md` describes. Write the result to `design/README.md`. In the first prototype round, name the platforms and why, in one line, so the human can correct them.
2. **Check the rollout stage.** Read `Current stage` in `design/README.md`. If a trigger for the next stage is met, follow **Rollout** below before you go on.
3. **Read the gallery.** Read `design/gallery.css` and the pages in `design/pages/`. If there is no `design/gallery.css` yet, this run also sets the visual identity: colours, fonts, spacing, and the primary action. Do that in ticket mode too.
4. **Prototype with the human.** Iterate in Claude Design: the Artifact tool's Design type, started with `quickstart` and intent `design`. If this session has no Artifact tool, ask the human to prototype in Claude Design and share the link. Show screens, not descriptions. Ask in chat; this is an exception to the Chat rule in `CLAUDE.md`, like the grill.
   - **Project mode:** set the identity if needed, and draw one rough page per main flow of the plan. Use realistic data. Leave states and edge cases out. Put all flows side by side and look for missing screens. Report each gap to `factory-plan` as a new ticket.
   - **Ticket mode:** start from the existing page for this ticket, if there is one. Redraw each page that a `🤖 replan: stale` comment on the ticket names, with the decision from that comment. Settle only what the ticket needs: each state the app can reach, empty and error cases, and the real copy.
   - **Variants.** Read `design-variants` from `## Steering` on the ticket, or on the plan ticket in project mode. If it is more than 1, draw that many prototypes of each new screen, and of the identity if this run sets it. Make them differ in layout or flow, not only in colour. Show them side by side and ask the human to pick one, or to combine parts of them. Then iterate on that one only. A page that already exists in the gallery is changed in place, without variants.
   - **Platforms.** Draw the variants on the primary platform only, the first in `Platforms`. Once the human has picked one, draw it on each other platform, and iterate on all of them together. Keep the structure, the flow, and the copy of the chosen variant; change only what the platform needs, such as navigation, layout, and controls. For a native platform, follow its conventions. When the human asks for a change, make it on every platform.
   - Stop when the human says the screens are right. Do not reopen identity decisions in ticket mode unless the human asks.
5. **Freeze into the gallery.** Write the result as static HTML in `design/pages/`, as `design/README.md` describes. One file per screen state, covering every platform. Use only `design/gallery.css` for styles. A page that the ticket changes must show the change; a page that it does not touch stays as it is.
6. **Take screenshots.** Run `$V gallery <feature id> <page> <platform>` from the `verify` skill for each new or changed page, on each platform. Open each image and compare it with the prototype. Fix the HTML until they match.
7. **Commit** to the ticket branch from the naming rule (in project mode, the plan ticket's branch) with the `Factory-Issue` trailer. Push. Attach the screenshots to the Linear ticket.
8. **Return** to the calling step: the platforms, the list of gallery pages with one line each, and any gaps found in project mode.

## Rollout

`design/README.md` lists the stages and the trigger for each. The gallery grows one stage at a time, and only when the trigger is met.

1. Compare the gallery with the trigger of the stage after `Current stage`.
2. Stage 1 is the exception: do its work in this run, and set `Current stage: 1` in the same commit.
3. For a later stage, if the trigger is met, search the Linear team for an open ticket titled `Gallery stage <n>`. If there is none, create it with the work that the stage lists. Do not give it the `ui` label: it changes the gallery's structure, not a screen. Tell the human in chat in one line, with the link.
4. Go on with this run. The stage ticket goes through the factory like any other ticket, and it updates `Current stage`.

## Done when

The gallery pages are committed and pushed, their screenshots are on the Linear ticket, and the calling step has the list of pages.
