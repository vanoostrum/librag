---
name: factory-spec
description: Factory step 1. Turn a feature description or a Linear ticket into a spec with testable acceptance criteria, then stop at the spec gate. Use when the human asks to work on a ticket or describes a new feature.
---

# factory-spec

Read the factory config and rules in `CLAUDE.md` first.

## Input

One of:
- a ticket key, e.g. `LIBRAG-12`;
- a feature description typed by the human.

## Steps

1. **Get the ticket.**
   - Ticket key: read it, with all comments.
   - Description: if it is truly ambiguous, ask at most 2 short questions. Then create a ticket in the Linear team from the config, with a short title and the description. Tell the human the key.
2. Move the ticket to **In Progress**.
3. **Read the code** that the change touches, so the spec fits what exists.
4. **Write the spec** into the ticket description, below the original text, under `## Spec`:
   - **Goal:** one or two sentences.
   - **Scope:** what changes.
   - **Out of scope:** what does not.
   - **Acceptance criteria:** a numbered list. Each one is testable and observable, e.g. "GET /version returns 200 with `{"version": "<pyproject version>"}`".
   - **Plan:** a few ordered tasks, each small enough to test on its own.
   - **Risks:** only if there are any.
   If a spec already exists and the human gave feedback, update it instead and note what changed.
5. **Gate.** Post `🤖 Gate: spec` with the acceptance criteria and "Reply approve, or give feedback." Ask the same in chat. Stop.

## Done when

The ticket has a `## Spec` section and a `🤖 Gate: spec` comment, and the human has been asked.

## Next

After approval (see Gates in `CLAUDE.md`), continue with `factory-build`.
