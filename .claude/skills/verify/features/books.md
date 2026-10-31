# Books

A client uploads an EPUB with `POST /api/books` and gets the new book back in `queued`. The worker parses it in the background into passages, and `GET /api/books` lists the books, newest first, with their status and passage count. After parsing, a book stays in `indexing` with 0 of N passages indexed until indexing exists (LIBRAG-24).

## Sub-features

- `books-upload` returns 202 with the book: `id`, `title`, `author`, `status` `"queued"`, `passages_indexed` 0, `passages_total` null, `error` null and `uploaded_at`.
- `books-parsed` shows the book in `indexing` with `passages_indexed` 0 and `passages_total` above 0, within a few seconds of the upload.
- `books-list` returns `{"books":[...]}`, newest first.
- `books-duplicate` returns 409 with `error` and the existing `book_id`, for the same file or another file with the same book ID.
- `books-unreadable` returns 422 with `{"error":"The file is not a readable EPUB"}`, or `{"error":"The EPUB has no title"}`.
- `books-too-large` returns 413 for a file over `LIBRAG_MAX_UPLOAD_MB` (50 by default).
- `books-no-text` ends in `failed` with `"error":"No text found in the EPUB"`.

## How to get to it (user POV)

- Send `POST /api/books` with the EPUB in the multipart field `file`, as the Library page will.
- Send `GET /api/books` to see the books and their status.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.
- The library is empty for the exact list bodies below. If an earlier recipe uploaded books, reset the library as the README says.

Set up the fixtures and the upload command once:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/books && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
d = '$E'
open(f'{d}/book.epub', 'wb').write(make_epub())
open(f'{d}/same-id.epub', 'wb').write(make_epub(FixtureBook(title='Other title')))
open(f'{d}/no-title.epub', 'wb').write(make_epub(FixtureBook(identifier='x', title=None)))
open(f'{d}/no-text.epub', 'wb').write(make_epub(FixtureBook(identifier='empty', chapters=(FixtureChapter('<p> </p>'),))))
"
post() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -F "file=@$1" $URL/api/books | tee $E/$2.txt; }
```

- **Upload.** Run `post $E/book.epub upload`. Status is `202` and the body is the book in `queued`, with `passages_total` null.
- **Parsed.** Wait 3 seconds, then run `$V get books /api/books`. Status is `200`; the book is in `indexing` with `passages_indexed` 0 and `passages_total` 1.
- **Same file.** Run `post $E/book.epub same-file`. Status is `409` and the body is `{"error":"This file is already in the library","book_id":"<id>"}`.
- **Same book ID.** Run `post $E/same-id.epub same-id`. Status is `409` and the body is `{"error":"A book with this ID is already in the library","book_id":"<id>"}`.
- **Not an EPUB.** Run `post pyproject.toml not-epub`. Status is `422` and the body is `{"error":"The file is not a readable EPUB"}`.
- **No title.** Run `post $E/no-title.epub no-title`. Status is `422` and the body is `{"error":"The EPUB has no title"}`.
- **No text.** Run `post $E/no-text.epub no-text`, wait 3 seconds, then `$V get books /api/books`. The newest book is in `failed` with `"error":"No text found in the EPUB"`.
- **Too large.** Run `head -c 52428801 /dev/zero > $E/big.bin && post $E/big.bin too-large`. Status is `413` and the body is `{"error":"The file is larger than 50 MB"}`.

## Gotchas

- Uploads change the library for the rest of the run. Drive this feature last, or reset the library before a recipe that needs it empty.
- The `id` is the first 16 hex characters of the SHA-256 of `dc:identifier`, so the same fixture always gets the same ID.
- `passages_total` is null until the worker has parsed the book. Poll `GET /api/books` rather than expecting it at once.
- The worker needs the `cl100k_base` tokenizer file. It downloads it on first use, unless `TIKTOKEN_CACHE_DIR` holds a copy; see project-verify.
