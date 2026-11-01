# Books

A client uploads an EPUB with `POST /api/books` and gets the new book back in `queued`. The worker parses it in the background into passages, embeds them and indexes them in Qdrant (collection `passages_fake` with the test settings), and `GET /api/books` lists the books, newest first, with their status, passage counts and embedding tokens and cost.

## Sub-features

- `books-upload` returns 202 with the book: `id`, `title`, `author`, `status` `"queued"`, `passages_indexed` 0, `passages_total` null, `error` null, `embedding_tokens` 0, `embedding_cost_usd` 0.0, `uploaded_at`, and `index_configuration` with `passage_target_tokens` 350, `passage_overlap_tokens` 50, `tokenizer` `"cl100k_base"` and `embedding_model` null.
- `books-indexed` shows the book in `indexed` with `passages_indexed` equal to `passages_total`, `embedding_tokens` above 0 and `embedding_cost_usd` 0.0 (the fake embedder), within a few seconds of the upload. Its `index_configuration.embedding_model` is `"fake"`.
- `books-points` shows the book's points in Qdrant: one per passage, with the payload `book_id`, `title`, `author`, `text`, `position`, `chapter_title`, `section_title`, `spine_index`, `first_paragraph` and `last_paragraph`.
- `books-list` returns `{"books":[...]}`, newest first.
- `books-duplicate` returns 409 with `error` and the existing `book_id`, for the same file or another file with the same book ID.
- `books-unreadable` returns 422 with `{"error":"The file is not a readable EPUB"}`, or `{"error":"The EPUB has no title"}`.
- `books-too-large` returns 413 for a file over `LIBRAG_MAX_UPLOAD_MB` (50 by default).
- `books-unpacks-too-large` refuses a zip bomb: an upload whose package file unpacks to over 32 MB is 422, and a book whose chapters unpack to over 32 MB each, or over 256 MB together, ends in `failed`. The route tests cover these; the recipe does not drive them.
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
- **Indexed.** Wait 3 seconds, then run `$V get books /api/books`. Status is `200`; the book is in `indexed` with `passages_indexed` 1, `passages_total` 1, `embedding_tokens` above 0 and `embedding_cost_usd` 0.0.
- **Points.** In process mode, run `Q=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/qdrant-port); curl -sS $Q/collections/passages_fake | tee $E/collection.txt` and `curl -sS -X POST $Q/collections/passages_fake/points/scroll -H 'content-type: application/json' -d '{"limit":10,"with_payload":true}' | tee $E/points.txt`. The collection has the `dense` vector (size 256, Cosine) and the `bm25` sparse vector (modifier `idf`); there is one point with the book's payload.
- **Same file.** Run `post $E/book.epub same-file`. Status is `409` and the body is `{"error":"This file is already in the library","book_id":"<id>"}`.
- **Same book ID.** Run `post $E/same-id.epub same-id`. Status is `409` and the body is `{"error":"A book with this ID is already in the library","book_id":"<id>"}`.
- **Not an EPUB.** Run `post pyproject.toml not-epub`. Status is `422` and the body is `{"error":"The file is not a readable EPUB"}`.
- **No title.** Run `post $E/no-title.epub no-title`. Status is `422` and the body is `{"error":"The EPUB has no title"}`.
- **No text.** Run `post $E/no-text.epub no-text`, wait 3 seconds, then `$V get books /api/books`. The newest book is in `failed` with `"error":"No text found in the EPUB"`.
- **Too large.** Run `head -c 52428801 /dev/zero > $E/big.bin && post $E/big.bin too-large`. Status is `413` and the body is `{"error":"The file is larger than 50 MB"}`.

## Gotchas

- Uploads change the library for the rest of the run. Drive this feature last, or reset the library before a recipe that needs it empty.
- The `id` is the first 16 hex characters of the SHA-256 of `dc:identifier`, so the same fixture always gets the same ID.
- `passages_total` is null until the worker has parsed the book, and the book is in `indexing` while its batches are embedded. Poll `GET /api/books` rather than expecting `indexed` at once.
- Qdrant computes the BM25 vectors on the server (`qdrant/bm25`). The Python client needs `cloud_inference=True` for that, or it tries to load fastembed.
- The worker needs the `cl100k_base` tokenizer file. It downloads it on first use, unless `TIKTOKEN_CACHE_DIR` holds a copy; see project-verify.
