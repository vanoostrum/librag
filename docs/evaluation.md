# Retrieval evaluation

The retrieval evaluation measures how well search finds the passages that answer a question. It runs the evaluation set in `eval/retrieval.toml` through `POST /api/rag/search` and reports Recall@5, Recall@10, Recall@20 and MRR for each retrieval stage: dense, BM25, fusion, and fusion with rerank. You run it by hand, on your own machine. It never runs in CI.

## Run it

Start your normal stack with the real providers, so search uses the OpenAI embedder and the CrossEncoder:

```bash
export OPENAI_API_KEY=sk-...
docker compose up -d --build --wait
scripts/eval-retrieval
```

The command does these steps:

1. It reads and checks the evaluation set. A fault, such as an unknown question type, stops it with the question ID.
2. It downloads each missing EPUB from Project Gutenberg into `eval/books/`, which git ignores.
3. It uploads each book that is not in the library, and waits until all 4 are `indexed`. Indexing the 4 books with OpenAI costs about 2 cents.
4. It checks that each evidence quote is in a passage of its book, cut as the book's index configuration cuts it.
5. It runs every question through the search, with 100 candidates per stage.
6. It prints the table and writes `eval-reports/retrieval-<timestamp>.json`, which git ignores.
7. It deletes the books that it uploaded.

Each search covers only the 4 evaluation books, so your own books never show up in the results. The command deletes only the books that it uploaded itself. If one of the books was already in your library, it uses that copy and leaves it there.

| Command or variable | Effect |
|---|---|
| `scripts/eval-retrieval --keep-books` | Keeps the evaluation books in the library after the run. The next run then uploads nothing and reports the books as present. |
| `scripts/eval-fetch-books` | Only steps 2 and 3: downloads and indexes the books. |
| `LIBRAG_EVAL_URL` | The stack to evaluate. The default is `http://localhost:8000`. |

The command stops with a message when the stack is not reachable, when a book fails to index, when a book is indexed with another embedding model than search uses, or when a question's `authors` filter names no evaluation book.

## Read the report

The table has one block for all questions with evidence, then one block per question type. Each row is a stage:

- **Recall@K** is the share of a question's evidence quotes that the stage found in its first K passages, averaged over the questions. 1.0 means every quote was in the top K.
- **MRR** is the mean of 1 / the rank of the first passage that holds any quote. 1.0 means the first passage always held one.

The `rerank` row is the order that chat uses for its context. Compare it with `fusion` to see what the reranker adds.

Negative questions have no answer in the books, so they have no recall. The table lists each one with its top rerank score instead. A later threshold on that score can make chat say "not in the books".

If a quote is in no passage of its book, the table lists it under "Evidence quotes that no passage contains". Fix the quote in the set: copy it from the book again, or shorten it so it does not cross a passage boundary.

The JSON report holds the same metrics, and for each question the first relevant rank in each stage and the rank of each quote. It also records the search settings, each book's index configuration, and the number of books in the library. BM25 weighs words by how rare they are in the whole collection, so your own books shift the BM25 scores a little. Compare two runs only when the rest of the library is the same.

## The evaluation set

`eval/retrieval.toml` lists the 4 books by their Project Gutenberg number, then the questions:

```toml
[[questions]]
id = "conceptual-creature-wicked"
type = "conceptual"
question = "How does the creature explain why he turned to evil?"
evidence = [
  { book = "frankenstein", quote = "I was benevolent and good; misery made me a fiend." },
]
```

- `type` is `factual`, `conceptual`, `cross-book`, `indirect` or `negative`. A cross-book question needs quotes from at least 2 books. A negative question has no `evidence`.
- An evidence quote is one sentence or less from the book's own text. A passage holds the quote when it contains it after case, whitespace and punctuation are folded, so the quote still matches when the passage size changes.
- `books` (book keys) or `authors` (as `GET /api/books` shows them) narrow a question's search. Without them, the question searches all 4 books.

Each quote counts as one relevant item. A passage that holds two quotes that were not found before takes two places in the ranking, so in that rare case the later ranks move down by one.
