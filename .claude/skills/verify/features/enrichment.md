# Enrichment

With `LIBRAG_ENRICHMENT=on`, the worker writes a context line for each passage while it indexes a book, and indexes the line with the passage for dense and BM25 search. The stack uses the fake enricher, whose line is `About <chapter heading>: <first five words>`. `POST /api/rag/search` returns the line as `context` on each result and candidate, and `text` stays the passage's own text. Chat citations never hold the line. `GET /api/books` shows the enrichment model, tokens and cost. Enrichment is part of the index configuration, so with `LIBRAG_REINDEX_ENABLED=on` a change of it marks books out of date, and reindex writes or removes the lines without a new parse.

## Sub-features

- `enrichment-off` with the switch off (the default): a book's `index_configuration.enrichment_model` is null, its enrichment tokens and cost are 0, and every search result and candidate has `context` null.
- `enrichment-search` with the switch on: each result and candidate has `context` `"About Part <n>: <first five words>"`, and `text` is the original passage text.
- `enrichment-books` with the switch on: the book has `index_configuration.enrichment_model` `"fake"`, `enrichment_input_tokens` and `enrichment_output_tokens` above 0, and `enrichment_cost_usd` 0.0.
- `enrichment-bm25` is covered by the route test `test_bm25_finds_a_passage_by_words_only_in_its_context_line`, not here. The fake line holds no word outside the indexed text except "About", which Qdrant's BM25 drops as a stopword.
- `enrichment-chat` with the switch on: `POST /api/chat` cites the original text only; the response holds no `About Part`.
- `enrichment-out-of-date` with both switches on: a book indexed with enrichment off shows "Out of date: indexed without enrichment" on the Library page. Reindex makes it `indexed` again with context lines and the same passage IDs. With enrichment off again, the note is "Out of date: indexed with enrichment".

## How to get to it (user POV)

- Start the stack with `LIBRAG_ENRICHMENT=on` (and `LIBRAG_REINDEX_ENABLED=on` for the out-of-date flow).
- Upload a book with `POST /api/books`, wait until it is `indexed`, then search, chat, and read `GET /api/books`.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold. Each part of the flow needs its own run, because the switches are read at launch.
- The library is empty.

Set up the fixture and the commands once per run:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/enrichment && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
open('$E/sea.epub', 'wb').write(make_epub(FixtureBook(identifier='urn:sea', title='Sea Stories', chapters=(
    FixtureChapter(paragraphs('The lighthouse keeper polished the brass lamp every evening.'), nav_title='Part 1'),
    FixtureChapter(paragraphs('Wild strawberries grew along the railway embankment.'), nav_title='Part 2')))))
"
post() { curl -sS -D $E/$3.headers -w '\n%{http_code}\n' -H 'content-type: application/json' -d "$2" $URL$1 | tee $E/$3.txt; }
upload() { curl -sS -D $E/$1.headers -w '\n%{http_code}\n' -F "file=@$E/sea.epub" $URL/api/books | tee $E/$1.txt; }
SEA=$(python3 -c "import hashlib; print(hashlib.sha256(b'urn:sea').hexdigest()[:16])")
```

- **Off.** Launch with `$V launch`. Run `upload upload-off`, wait 3 seconds, then `$V get enrichment /api/books`: `enrichment_model` null and the enrichment fields 0. Run `post /api/rag/search '{"query":"lighthouse"}' search-off`: every `context` is null. Keep this run for the out-of-date flow, or `$V cleanup`.
- **On.** On a new run, launch with `LIBRAG_ENRICHMENT=on $V launch`. Run `upload upload-on`, wait 3 seconds, then `$V get enrichment /api/books`: `enrichment_model` `"fake"`, tokens above 0, cost 0.0. Run `post /api/rag/search '{"query":"lighthouse strawberries"}' search-on`: each result and candidate has `context` `"About Part 1: The lighthouse keeper polished the"` or `"About Part 2: Wild strawberries grew along the"`, and `text` is the passage text.
- **Chat.** On the same run, `post /api/chat '{"question":"Who polished the lamp?"}' chat`: status 200; each citation's `text` is a passage text, and the body has no `About Part`.
- **Out of date.** On a new run, launch with `LIBRAG_REINDEX_ENABLED=on LIBRAG_ENRICHMENT=on $V launch`. Run `upload upload-reindex` and wait 3 seconds. Stage a book indexed before the switch: `uv run python -c "import sqlite3; db = sqlite3.connect('.verify/$LIBRAG_VERIFY_RUN/run/data/librag.db'); db.executescript('update books set enrichment_model=null; update passages set context=null'); db.commit()"`. `$V get enrichment /library/books` shows "Out of date: indexed without enrichment". Note the passage IDs from a search, then run `post /api/books/$SEA/reindex '{}' reindex`: 202. After 3 seconds the book is `indexed`, the note is gone, and search shows the context lines with the same passage IDs.

## Gotchas

- The switches are read when the api and the worker start. Launch a new run to change them.
- The fake enricher costs 0, so `enrichment_cost_usd` is 0.0 even when enrichment is on. Its tokens count words.
- Do not test BM25 on the fake line: "about" is a BM25 stopword, and its other words are in the passage and chapter heading too.
- The Library page shows out-of-date notes only with `LIBRAG_REINDEX_ENABLED=on`.
