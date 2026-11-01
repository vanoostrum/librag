# Live run

A live run is the e2e suite against the real AI providers. You start it by hand, on your own machine, with your own API keys. It stops at a cost cap and reports the tokens and cost of each model. It never runs in CI.

## Run it

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
scripts/e2e-live
```

The command does these steps:

1. It checks that `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are set. If one is missing, it names the key and stops before it starts anything.
2. It builds the image and starts the stack as its own Compose project, `librag-live`, on port 8100. The stack uses the real providers: the OpenAI embedder, the CrossEncoder reranker in the image, and both default chat models.
3. It runs `tests/e2e/` with `LIBRAG_E2E_LIVE=1`.
4. It prints the usage table and writes the report.
5. It tears down `librag-live` with its volumes. It does this also when a test fails or the stack does not start.

The live stack has its own volumes, so it never touches the data of your local `librag` stack. Pass pytest arguments after the command to run part of the suite, for example `scripts/e2e-live -k cross_book`.

Docker must be running. The first build downloads the reranker model into the image, so it can take a few minutes.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `LIBRAG_LIVE_BUDGET_USD` | `2` | The cost cap in dollars. |
| `LIBRAG_LIVE_PORT` | `8100` | The port of the live stack's app. |
| `LIBRAG_LIVE_QDRANT_PORT` | `6433` | The port of the live stack's Qdrant. |

For example, `LIBRAG_LIVE_BUDGET_USD=0.5 scripts/e2e-live` stops at 50 cents.

## The cost cap

The cost of a run is the sum of `usage.cost_usd` of each chat answer and `embedding_cost_usd` of each indexed book. The suite checks this sum before each chat request. Once the sum reaches the cap, each remaining chat test fails with `budget reached` and sends no request. So a run can pass the cap by the cost of one request at most.

LiteLLM can lack the price of a model. Its cost is then unknown, and the cap cannot count it. The table shows `unknown`, the JSON shows `null`, and the report prints a warning for each model with an unknown cost.

A chat request that fails with 502 returns no usage, so the cap does not count it either.

## The report

At the end of the run, the command prints one row per model: requests, input and output tokens, cost, and mean LLM latency. A last row gives the embedding tokens and cost of the indexed books.

The same data goes to `e2e-reports/<timestamp>.json`, which git ignores. The JSON also keeps the question and the answer parts of each request. When a live test fails, for example because a model cited only one book, read its answer there.

## What a live run checks

The suite runs the same tests as the required `e2e` check, with two changes:

- The cross-book tests use the larger live books from `tests/e2e/books.py`. These books have distractor passages that share words with the question but do not answer it. The answer of each model must cite both selected books, through `POST /api/chat` and the stream route. The rerank stage must use the CrossEncoder, not the fake.
- Tests marked `fake_only` check what the fakes answer, so a live run skips them.

The checks are loose. They check structure, citations and which books are cited, never the exact answer text.
