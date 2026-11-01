# Chat page

The Chat page at `/chat` lets the user ask questions about their library and read each answer as it streams from `POST /api/chat/stream`: progress lines first, then each checked part with its cited passages. Turns stack in the page with the ask bar at the bottom; "New conversation" or a reload clears them. A book picker above the ask bar limits the search to the ticked books, grouped by author. The browser remembers the last model picked. With no indexed book, the page says so and the ask bar is disabled. A failed answer shows the provider's message and "Try again". "How this answer was found" under an answer opens its diagnostics, built from the `done` event. The page matches the gallery pages in `design/pages/chat/`.

## Sub-features

- `chat-page-no-books`: with no indexed book, "No books are indexed yet", "Go to the Library" (to `/`), and a disabled ask bar with "Books: none".
- `chat-page-start`: with indexed books, "Ask your library", the model select with the configured models and the default selected, and "Books: All indexed books".
- `chat-page-picker`: the picker lists the indexed books by author. Ticking or unticking an author ticks or unticks their books. The toggle says "All indexed books", "N books" or "none". The next question sends the ticked books as `book_ids`, or no `book_ids` when all are ticked.
- `chat-page-stream`: asking shows "Searched your books · N passages found" and "Writing the answer…" with the parts that have arrived; the ask bar is disabled until `done`. Then the progress lines go and "How this answer was found" appears, closed.
- `chat-page-turns`: a follow-up sends the earlier turns as `turns`; turns stack. "New conversation" clears them.
- `chat-page-error`: an `error` event shows "The model didn't answer: <message>" and "Try again", which asks again in place of the failed turn, with the turns before it. With no book ticked, "Try again" is disabled, like Ask.
- `chat-page-diagnostics`: opening "How this answer was found" sends no request and shows a summary (question; search query with "rewritten" only when it differs from the question; model, tokens in and out, cost or "cost unknown", time; each stage's count and time, "rerank off" without rerank, and the passages sent with their tokens), then one card per fused candidate in final order: rank, book, chapter and section, the first words (click for the full text), and Dense, BM25, Fusion and Rerank tags, "–" for a stage without the passage. Passages sent to the model have a green edge and "Sent to model". The first 20 cards show, then "Show all N candidates". A failed turn has no diagnostics.
- `chat-page-model`: the picked model is still selected after a reload.

## How to get to it (user POV)

- Open `/` and click "Chat" in the header, or open `/chat`.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.
- Node with Playwright, for `scripts/chat-browser.js`. The cloud container has both.
- For **No books**, the library has no indexed book: use a new run, as the README says.

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/chat-page && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
B=.claude/skills/verify/scripts/chat-browser.js
```

- **No books.** On an empty library, run `$V get chat-page /chat` (200, `text/html`, "No books are indexed yet"), then `node $B $URL $E no-books desktop` and `node $B $URL $E no-books mobile`. Compare `app_no_books_<platform>.png` with `$V gallery chat-page pages/chat/no-books.html <platform>`.
- **Index.** Upload three books by two authors, as in the Chat recipe's fixtures plus a second book by Ada Writer, and wait until `GET /api/books` shows them `indexed`.
- **Flow.** For each platform, run `node $B $URL $E chat <platform>`. The transcript `browser_chat_<platform>.txt` shows, in order:
  - unticking an author unticks their books, and ticking it ticks them again; with one book unticked the toggle says "Books: 2 books";
  - while streaming: the two progress lines, the first part, `askDisabled: true`; the request has the two ticked `book_ids`;
  - answered: no progress lines, a book part and a synthesis, two sources, one diagnostics placeholder, `askDisabled: false`;
  - the follow-up request has the first turn in `turns`; two turns; after "New conversation" no turns and the intro is back;
  - the failed turn shows "The model didn't answer: Rate limit reached for gpt-6.1-terra. Try again in a minute."; a question asked after it is answered below it;
  - with no book ticked, both Ask and "Try again" are disabled;
  - "Try again" sends `turns: []` (no answered turn comes before the failed one), and the retried turn stays first, above the later turn;
  - after picking GPT 6.1 Terra and reloading, the model is `openai/gpt-6.1-terra` and the next request sends it;
  - `external requests: []`.
- **Diagnostics.** Also upload a 30-chapter book, so there are more than 20 candidates (the Chat recipe's `book` helper):
  `open(f'{d}/logbook.epub', 'wb').write(make_epub(book('urn:logbook', "The Keeper's Logbook", 'Ada Writer', *[f'Day {n}: the keeper logged the weather, the ships and the state of the lamp before the long night watch began.' for n in range(1, 31)])))`
  For each platform, run `node $B $URL $E diagnostics <platform>`. The transcript `browser_diagnostics_<platform>.txt` shows, in order:
  - the panel closed after the answer; `requests while opening the panel: []`;
  - the summary rows Question, Search query (no "rewritten"), Model, Retrieval; 20 cards, the first ones "Sent to model"; "Show all 30 candidates";
  - the first words open to the full text; after "Show all", 30 cards and no button;
  - the follow-up's search query ends in "rewritten";
  - rerank off (the wrapper empties the `done` event's rerank stage and sets `settings.rerank` false, since the stack always reranks): "rerank off" in the summary, `rerank tags ["Rerank –"]`, `fusion order true`;
  - `failed turn: {"diagnostics":false}`; `external requests: []`.
  Compare `app_diagnostics_<platform>.png` with `$V gallery chat-page pages/chat/diagnostics.html <platform>`, and `app_diagnostics_cards_<platform>.png` with `gallery_diagnostics_cards_<platform>.png`, which the script takes from the gallery page scrolled to the panel.
- **Gallery.** For each platform, compare `app_<state>_<platform>.png` with `$V gallery chat-page pages/chat/<page>.html <platform>`, for start, book-picker, streaming, answer, conversation and error.

Expected differences from the gallery: the books, questions, answer text, passage counts, diagnostics numbers, scores and first words (the stack uses fixture books and the fake LLM), the chapter titles of the sources ("Part 1"; fixture chapters have no section), the gallery's first source shown open, and the length of the conversation behind the ask bar. Anything else in layout, copy or look is a fail.

## Gotchas

- The fake LLM answers at once. `chat-browser.js` wraps the page's `fetch` so the server's events arrive one at a time, and holds them after the first part for the streaming screenshot.
- The fake LLM never fails, so for the error state the wrapper replaces the stream with an `error` event. The route tests cover the server's `error` events.
- Screenshots are taken with no element focused: the gallery draws no focus. In the app the ask bar shows a green outline while its input has focus.
- `localStorage` holds the model per browser profile; each script run starts with a new one.
