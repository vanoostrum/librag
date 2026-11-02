# Retrieval evaluation

The retrieval evaluation runs an evaluation set through `POST /api/rag/search` on a running stack and reports Recall@5, Recall@10, Recall@20 and MRR for the dense, BM25, fusion and rerank stages. `scripts/eval-fetch-books` downloads the set's EPUBs and indexes them; `scripts/eval-retrieval` does that too, then searches, prints a table, writes `eval-reports/retrieval-<timestamp>.json`, and deletes the books it uploaded. Every search covers only the set's books, and a book that was already in the library is used but never deleted.

## Sub-features

- `eval-fetch` uploads each book of the set that is not in the library, waits until all are `indexed`, and prints `All <n> evaluation books are indexed.`
- `eval-run` prints the metrics table (overall, then per question type), the negative questions with their top rerank score, and `Report: <path>`. The JSON has `metrics`, `questions` (each with `first_relevant_rank` per stage and the ranks of its quotes), `missing_quotes`, `search_settings`, `books` (with each `index_configuration`) and `library_books`.
- `eval-cleanup` deletes the books the run uploaded, and only those. With `--keep-books` they stay, and the next run prints `<title> is already in the library` and uploads nothing.
- `eval-errors` exits 1 with `eval: ...` on stderr when the stack is not reachable, a book fails to index, or the set has a fault (naming the question ID).

## How to get to it (user POV)

- Start a stack, then run `scripts/eval-retrieval` from the repo root. `LIBRAG_EVAL_URL` points it at the stack (default `http://localhost:8000`).
- The real set (`eval/retrieval.toml`) needs Project Gutenberg and the real providers, so drive the commands here with a fixture set and fixture EPUBs instead.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.
- The library is empty, or holds only books you want to see left alone.

Write a fixture set and its EPUBs. The command finds `pg<n>.epub` in the books folder, so it downloads nothing:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/evaluation && mkdir -p $E/books
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
def book(identifier, title, author, *texts):
    return FixtureBook(identifier=identifier, title=title, author=author, chapters=tuple(
        FixtureChapter(paragraphs(t), nav_title=f'Part {n}') for n, t in enumerate(texts, 1)))
d = '$E/books'
open(f'{d}/pg1.epub', 'wb').write(make_epub(book('urn:sea', 'Sea Stories', 'Ada Writer',
    'The lighthouse keeper polished the brass lamp every evening.',
    'Wild strawberries grew along the railway embankment.')))
open(f'{d}/pg2.epub', 'wb').write(make_epub(book('urn:harbour', 'Harbour Tales', 'Ben Author',
    'A submarine captain charted the coral reef at dawn.',
    'The lighthouse beam swept across the harbour fog.')))
"
cat > $E/set.toml <<'TOML'
[books.sea]
gutenberg = 1
title = "Sea Stories"
[books.harbour]
gutenberg = 2
title = "Harbour Tales"
[[questions]]
id = "f1"
type = "factual"
question = "Who polished the brass lamp?"
evidence = [{ book = "sea", quote = "polished the brass lamp" }]
[[questions]]
id = "x1"
type = "cross-book"
question = "Which lighthouse is described?"
evidence = [{ book = "sea", quote = "lighthouse keeper" }, { book = "harbour", quote = "lighthouse beam" }]
[[questions]]
id = "n1"
type = "negative"
question = "Who won the chess championship?"
TOML
ev() { LIBRAG_EVAL_URL=$URL uv run --group eval python -m librag.evaluation "$@" --set $E/set.toml --books-dir $E/books; }
```

- **eval-fetch.** `ev fetch | tee $E/fetch.txt`. It prints `uploading Sea Stories`, `uploading Harbour Tales` and `All 2 evaluation books are indexed.` `$V get evaluation /api/books` shows both in `indexed`.
- **eval-run, kept.** `ev run --keep-books --reports-dir $E/reports | tee $E/run-keep.txt`. It prints `Sea Stories is already in the library`, the table with `All questions with evidence (2 questions)`, `Factual (1 questions)`, `Cross-book (1 questions)`, the line for `n1`, and `Report: $E/reports/retrieval-<timestamp>.json`. The books are still in `GET /api/books`.
- **eval-run, cleaned up.** `ev run --reports-dir $E/reports | tee $E/run.txt`. The output ends with `deleted evaluation book <id>` for both books, and `GET /api/books` no longer lists them.
- **eval-errors.** `LIBRAG_EVAL_URL=http://127.0.0.1:9 uv run --group eval python -m librag.evaluation run --set $E/set.toml --books-dir $E/books 2>&1 | tee $E/unreachable.txt` exits 1 with `eval: the stack at http://127.0.0.1:9 is not reachable`.

## Gotchas

- The fixture stack uses the fake embedder and reranker, so the numbers say nothing about real retrieval quality. Only the real run, on a machine that can reach Project Gutenberg and OpenAI, does.
- ranx compiles its metrics with numba on first use, so the first `run` takes about a minute before the table appears.
- `eval/books/uploaded.json` (here `$E/books/uploaded.json`) records which books the evaluation uploaded to which stack URL. Deleting it makes the next run treat those books as the user's own and keep them.
