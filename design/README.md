# Design gallery

The gallery is the visual spec of LibRag. It shows how each screen looks before anyone builds it. The factory follows it literally: `factory-build` builds screens to match it, and `factory-review` compares the app with it.

The gallery is not a sign-off document. It is a living file in the repo, next to the code. When the look changes, the gallery changes in the same PR as the code.

Current stage: 0

## Layout

| Path | What |
|---|---|
| `design/gallery.css` | The gallery's stylesheet. It holds the visual identity: colours, fonts, spacing, and the primary action. It is separate from the app's stylesheet. |
| `design/pages/<screen>/<state>.html` | Demo pages. One static HTML file per screen state, such as `design/pages/search/empty.html`. |
| `design/components/` | From stage 2. Every component in every state that matters: hover, focus, disabled, error, light and dark. |
| `design/patterns/` | From stage 2. The rules for combining components, such as where the primary action sits and the space between items. |

## Rules for pages

- Static HTML with realistic data, not lorem ipsum. Real copy where the ticket settled it.
- Styles come only from `design/gallery.css`, linked with a relative path. No other CSS, no external fonts or scripts, so a page renders from a file without a server.
- One file per state that the app can reach. The file name is the state: `default`, `empty`, `error`, `loading`, and so on.
- Each page has exactly one primary action.
- Acceptance criteria cite pages by path, for example "GET /search with no results matches `design/pages/search/empty.html`".
- Take screenshots with `$V gallery <feature id> <page>` from the `verify` skill.

## Who changes the gallery

- `factory-design` adds and changes pages, with the human, before the spec gate.
- `factory-build` does not change the gallery, except for polish fixes asked at the merge gate. A polish fix changes the code and the gallery in the same PR.
- Feedback that changes the design, not only polishes it, goes back to `factory-design`.
- The replan check in `factory-next` marks the pages of later tickets stale when a decision changes their screen. `factory-design` redraws a stale page when its ticket is grilled.

## Rollout stages

The gallery grows in stages. At the start of each run, `factory-design` checks the trigger of the next stage. When the trigger is met, it creates a Linear ticket `Gallery stage <n>` with the work below. That ticket goes through the factory and sets `Current stage` above.

| Stage | Trigger | Work |
|---|---|---|
| 1. Pages | The first ticket with the `ui` label, or a plan with screens. `factory-design` does this work inside that ticket, without a stage ticket. | Add `design/gallery.css` with the visual identity, and the first pages in `design/pages/`. Set `Current stage: 1`. |
| 2. Components, patterns, and checks | Stage 1 is done and `design/pages/` holds 5 or more screens, or one element appears on 3 or more screens. | Extract `design/components/` and `design/patterns/` from the pages. Add `tests/design/`: Playwright tests over the gallery pages and the app's HTML routes that check WCAG AA contrast, that elements are visible, and that each page has one primary action that stands out. Add Playwright with `uv add --dev playwright` and a CI step that installs Chromium. Add `tests/design/` to the project table and the test seam rule in `CLAUDE.md`, and to `project-verify`. Set `Current stage: 2`. |
| 3. Coverage and sync | Stage 2 is done. | Add a test that every HTML route of the app has a gallery page. Add a recurring task that compares the gallery with the live app and opens a ticket for each difference. Set `Current stage: 3`. |

Stage 3 is the last stage. Usability in production, such as task completion rates, is out of scope until LibRag has users.
