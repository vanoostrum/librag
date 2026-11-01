# Library

The Library page at `/` lists the books as cards, newest first, with their status and indexing progress, and refreshes while a book is in progress. The user adds books with "Add a book" and the file picker, or by dropping files on the page. A refused upload shows a dismissable notice. `GET /library/books` returns the page's library region for that refresh. The page matches the gallery pages in `design/pages/library/`, without the Delete and Retry links (LIBRAG-14).

## Sub-features

- `library-empty`: with no books, the page says "Your library is empty" and shows the drop area, as `empty.html`.
- `library-cards`: a card per book with cover, title, author and status: "Waiting in the queue", "Reading the book", "Indexing · N%" with a progress bar, "Indexed · N passages", or "Failed: <error>", as `default.html`.
- `library-lede`: the lede counts the books ("Five books."), then "Ask about any of them in Chat once they are indexed."
- `library-refresh`: `GET /library/books` returns the region with `hx-trigger="every 2s"` while a book is queued, parsing or indexing, and without it otherwise.
- `library-add`: "Add a book" opens a file picker for several `.epub` files; each chosen file is uploaded and appears as a card.
- `library-drop`: files dragged over the page show "Drop to add to your library", as `dropping.html`; dropping uploads each one.
- `library-notices`: a refused upload shows a notice, as `upload-error.html`: 409 "*<title>* is already in your library.", 422 "*<file name>* isn't an EPUB we can read.", 413 "*<file name>* is larger than 50 MB." The notices survive the refresh, and "Dismiss" removes one.
- `library-local-only`: the page loads no script, stylesheet or font from another host.

## How to get to it (user POV)

- Open `http://127.0.0.1:<port>/` in a browser. Click "Add a book", or drag EPUB files onto the page.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold, in process mode: the staging step writes to the run's SQLite file.
- The library is empty at the start. Reset it as the README says before part 2.
- Node with Playwright, for `scripts/library-browser.js`. The cloud container has both.

Set up once per run:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/library && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
DB=sqlite:///.verify/$LIBRAG_VERIFY_RUN/run/data/librag.db
B=.claude/skills/verify/scripts/library-browser.js
S=.claude/skills/verify/scripts/library-states.py
F=.verify/$LIBRAG_VERIFY_RUN/fixtures && mkdir -p $F
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub
books = {
    'scanned-atlas': FixtureBook(identifier='atlas', title='scanned-atlas.epub', author=None, chapters=(FixtureChapter('<p> </p>'),)),
    'meditations': FixtureBook(identifier='med', title='Meditations', author='Marcus Aurelius'),
    'antifragile': FixtureBook(identifier='anti', title='Antifragile', author='Nassim Nicholas Taleb'),
    'black-swan': FixtureBook(identifier='swan', title='The Black Swan', author='Nassim Nicholas Taleb'),
    'noise': FixtureBook(identifier='noise', title='Noise', author='Kahneman, Sibony, Sunstein'),
    'thinking': FixtureBook(identifier='tfs', title='Thinking, Fast and Slow', author='Daniel Kahneman'),
    'dropped-1': FixtureBook(identifier='drop1', title='The Bed of Procrustes', author='Nassim Nicholas Taleb'),
    'dropped-2': FixtureBook(identifier='drop2', title='Fooled by Randomness', author='Nassim Nicholas Taleb'),
}
for name, book in books.items():
    open(f'$F/{name}.epub', 'wb').write(make_epub(book))
"
printf 'not a zip' > $F/holiday-photos.zip
head -c 52428801 /dev/zero > $F/complete-encyclopedia.epub
```

`library-states.py` sets the status and passage counts of the books, by title, to those of a gallery page, because the worker passes through `parsing` and `indexing` too fast for a screenshot.

**Part 1, on an empty library: empty, add, default.**

- **Empty.** Run `$V get library /`. Status `200`, `content-type: text/html; charset=utf-8`, and the body has `Your library is empty` and no `book-card`. Run `$V get library /library/books`: the body starts with `<div id="library" class="library">`, with no `hx-trigger`. Run `$V screenshot library / desktop` and `$V screenshot library / mobile`, then rename them to `app_empty_<platform>.png`. Take `$V gallery library pages/library/empty.html <platform>` for both.
- **Add.** Run `node $B $URL $E add desktop $F/scanned-atlas.epub $F/meditations.epub $F/black-swan.epub $F/noise.epub $F/thinking.epub`. The transcript `browser_add_desktop.txt` shows `multiple=true accept=.epub,application/epub+zip`, five cards in "Waiting in the queue" with Thinking, Fast and Slow first, `"polling":"every 2s"`, and `external requests: []`.
- **Refresh stops.** Wait 3 seconds, then `$V get library /library/books`. No `hx-trigger`: the worker has indexed four books and failed `scanned-atlas.epub`.
- **Default.** Run `uv run python $S $DB default`. Run `$V get library /library/books`: it has `hx-trigger="every 2s"` again, since Meditations is queued. Take `$V screenshot library / <platform>` (rename to `app_default_<platform>.png`) and `$V gallery library pages/library/default.html <platform>` for both platforms. The lede is "Five books."; the Black Swan card shows "Indexing · 63%" and its bar.

**Part 2, on a new empty run: upload error, dropping.** Reset the library and repeat the setup.

- **Books.** Run `node $B $URL $E add desktop $F/meditations.epub $F/antifragile.epub $F/black-swan.epub $F/thinking.epub`, wait 3 seconds, then `uv run python $S $DB upload-error`.
- **Refused uploads.** For each platform, run `node $B $URL $E refused <platform> $F/thinking.epub $F/holiday-photos.zip $F/complete-encyclopedia.epub`. The transcript shows the three notices in the copy above, the same three after a refresh, and two after "Dismiss". Compare `app_upload_error_<platform>.png` with `$V gallery library pages/library/upload-error.html <platform>`.
- **Dropping.** Run `node $B $URL $E drop desktop $F/dropped-1.epub` and `node $B $URL $E drop mobile $F/dropped-2.epub`. The transcript shows `"overlayVisible":true` while dragging, then the dropped book as the first card and the overlay gone. Compare `app_dropping_<platform>.png` with `$V gallery library pages/library/dropping.html <platform>`.

Expected differences from the gallery: the cover colours (the app picks them from the book ID), the failed book's error text (the real one is "No text found in the EPUB"), the Delete and Retry links (LIBRAG-14), and the books behind the dropping overlay. Anything else in layout, copy or look is a fail.

## Gotchas

- `$V screenshot` names the file `root_<platform>.png` for `/`. Rename it after each state, or the next state overwrites it.
- The Chat link goes to `/chat`, which returns 404 until the Chat page exists (LIBRAG-16).
- A dropped file that is already in the library gives a 409 notice instead of a card. Use a different fixture for each drop.
- `library-states.py` writes to the run's database directly. In compose mode the database is inside the `api` container; use process mode for this recipe.
