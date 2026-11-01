# Book actions

A client deletes a book with `DELETE /api/books/{id}` and retries a failed or interrupted one with `POST /api/books/{id}/retry`. With `LIBRAG_REINDEX_ENABLED=on`, it reindexes one indexed book with `POST /api/books/{id}/reindex`, or every out-of-date book with `POST /api/books/reindex-out-of-date`; with the switch off, both answer 404. Each action leaves the other books alone, and search shows the result.

## Sub-features

- `book-delete`: 204 with no body. The book is gone from `GET /api/books` and from search. A second delete is 404 `{"error":"No book with this ID"}`.
- `book-delete-busy`: 409 `{"error":"The book is queued or being indexed"}` while the book's job is queued or running.
- `book-retry`: 202 with the book in `queued` for a failed or interrupted book; the worker then indexes it. 409 `{"error":"Only a failed or interrupted book can be retried"}` otherwise.
- `book-interrupted`: a book left in `parsing` or `indexing` with no queued or running job lists as `failed` with `"error":"indexing was interrupted"`.
- `book-reindex`: with the switch on, 202 with the book in `queued`; search leaves it out until the worker has indexed it again, with the same passage count. 409 `{"error":"Only an indexed book can be reindexed"}` for a book that is not indexed.
- `book-reindex-out-of-date`: with the switch on, 202 `{"book_ids":[...]}` with the out-of-date books, which the worker then reindexes; the others stay `indexed`.
- `book-reindex-off`: with the switch off, both reindex routes are 404 `{"error":"Reindexing is turned off"}`.

## How to get to it (user POV)

- On the Library page: Delete, Retry and Reindex on a book card, and "Reindex N out-of-date books" at the top. See [Library](./library.md).
- Through the API: the routes above, with `curl`.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold, in process mode.
- Two runs: one launched as usual (switch off), and one launched with `LIBRAG_REINDEX_ENABLED=on $V launch` (the env file does not set it, so the exported value holds).

Set up in each run:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/book-actions && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
DB=.verify/$LIBRAG_VERIFY_RUN/run/data/librag.db
SQL() { uv run python -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute(sys.argv[2]); c.commit()' "$DB" "$1"; }
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
for name, text in (('sea', 'The lighthouse keeper polished the brass lamp.'), ('harbour', 'A submarine charted the coral reef.')):
    open(f'$E/{name}.epub', 'wb').write(make_epub(FixtureBook(identifier=f'urn:{name}', title=name.title(), chapters=(FixtureChapter(paragraphs(text)),))))
"
for b in sea harbour; do curl -s -F file=@$E/$b.epub $URL/api/books; echo; done
sleep 3
curl -s $URL/api/books | tee $E/list_before.txt
```

Note the IDs of Sea and Harbour from the list (`SEA`, `HARBOUR`). Save every response below to `$E/<name>.txt` with `curl -s -i ... | tee`.

**Switch off:**

- `curl -s -i -X POST $URL/api/books/$SEA/reindex` and `curl -s -i -X POST $URL/api/books/reindex-out-of-date`: both 404 `{"error":"Reindexing is turned off"}`.
- Interrupted: `SQL "update books set status='indexing' where id='$SEA'"`, then `GET /api/books` lists Sea as `failed` with `indexing was interrupted`. `POST /api/books/$SEA/retry` is 202 with `"status":"queued"`; after 2 seconds Sea is `indexed`. Retry again: 409.
- Delete: `curl -s -X POST $URL/api/rag/search -H 'content-type: application/json' -d '{"query":"lighthouse keeper submarine"}'` has passages of both books. `curl -s -i -X DELETE $URL/api/books/$SEA` is 204. The same search has no passage with `"book_id":"$SEA"`. A second delete is 404.

**Switch on** (the second run, same setup):

- Reindex: `POST /api/books/$SEA/reindex` is 202 with `"status":"queued"`; after 2 seconds Sea is `indexed` with the same `passages_total`, and the search above has each of its passages once.
- Out of date: `SQL "update books set embedding_model='openai/text-embedding-3-small' where id='$SEA'"`. `POST /api/books/reindex-out-of-date` is 202 `{"book_ids":["$SEA"]}`; Harbour stays `indexed` throughout. After 2 seconds a second call returns `{"book_ids":[]}`.
- Busy: upload a third book and, within the same second, `curl -s -i -X DELETE` it: 409, or 204 if the worker was faster. The route tests cover the 409.

## Gotchas

- The fake worker indexes a small book in well under a second, so the in-progress states pass quickly. To see one, pause the worker with `kill -STOP $(cat .verify/$LIBRAG_VERIFY_RUN/run/worker.pid)`, and resume it with `kill -CONT`.
- The embedding-model change is staged in the database: the fake embedder is always `fake`, so only a staged book can be out of date by model.
