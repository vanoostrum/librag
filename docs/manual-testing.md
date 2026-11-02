# Manual testing and settings

This page says how to try LibRag by hand, which scripts measure it, and every setting that switches a feature on or tunes indexing, retrieval and the models. The automated tests are in the [README](../README.md#development) and the `project-verify` skill.

## Put your keys in `.env`

Copy the example file in the repo root and fill in the keys:

```bash
cp .env.example .env
```

| Key | Needed for |
|---|---|
| `OPENAI_API_KEY` | Embedding passages, which every upload does in live mode, and the GPT chat model. |
| `ANTHROPIC_API_KEY` | The Claude chat model, and the enrichment model when `LIBRAG_ENRICHMENT` is on. |
| `GEMINI_API_KEY`, `XAI_API_KEY` | Only for chat models of those providers that you add to `LIBRAG_CHAT_MODELS`. |

Docker Compose reads `.env` from the repo root and passes each variable that `compose.yaml` lists to the api, the worker and `migrate`. A variable set in the shell wins over `.env`. git ignores `.env`, so your keys stay out of the repo.

The scripts that call the providers from your machine (`scripts/e2e-live` and `scripts/eval-answers run`) read the keys from the shell, not from `.env`. Keep a copy of the keys in a file outside the repo, such as `~/.config/librag/live.env`, and load it into the shell first:

```bash
set -a; source ~/.config/librag/live.env; set +a
```

`.env` also reaches stacks that the scripts and the test overlay start, because they use the same `compose.yaml`. A switch such as `LIBRAG_DECOMPOSE=on` in `.env` is therefore on in those stacks too. Comment it out before a run that should use the defaults.

## Run the stack

With the real providers, using the keys in `.env`:

```bash
docker compose up -d --build --wait
```

Without keys, with the deterministic fake providers:

```bash
docker compose -f compose.yaml -f compose.test.yaml up -d --build --wait
```

The app is at <http://localhost:8000>. `GET /health` returns 200 when Qdrant, the database and the worker are ready. After a change to `.env`, run the same `up` command again: Compose recreates the containers whose settings changed. Add `--build` after a `git pull`, so the image has the new code. `docker compose down -v` stops the stack and deletes its books.

The fakes give answers and scores that do not depend on meaning, so use them to check the flow, and the real providers to judge quality. In live mode, each upload costs its embeddings (about 2 cents for the 4 evaluation books together) and each chat question its LLM calls; the chat diagnostics show the cost of each answer.

## Try it by hand

You need an EPUB. Any book from [Project Gutenberg](https://www.gutenberg.org) works, as do the four evaluation books that `scripts/eval-fetch-books` downloads into `eval/books/`.

**Library** (<http://localhost:8000>)

1. Drop the EPUB on the page, or pick it. The book shows as queued, then indexing, then indexed. A file over `LIBRAG_MAX_UPLOAD_MB`, or one that is not an EPUB, shows an error.
2. Delete a book. The page asks first.
3. Stop the worker (`docker compose stop worker`) and upload a book, to see the book wait in queued, and `/health` answer 503 once the worker's last heartbeat is 30 seconds old. `docker compose start worker` picks it up.
4. With `LIBRAG_REINDEX_ENABLED=on`, change an indexing setting, such as `LIBRAG_PASSAGE_TARGET_TOKENS=250`, and restart. Each book shows "Out of date: passages of 350 tokens", and Reindex, or "Reindex N out-of-date books", indexes it again.

**Chat** (<http://localhost:8000/chat>)

1. Ask a question about one book. The answer streams in, with citations to passages.
2. Pick books in the book picker to search only those, and pick another model.
3. Ask a follow-up, such as "and what did she do next?". With `LIBRAG_QUERY_REWRITE=on`, "How this answer was found" shows the rewritten search query.
4. Open "How this answer was found" for the search query, the model, tokens and cost, and the passages of each stage: dense, BM25, fusion and rerank.
5. With `LIBRAG_DECOMPOSE=on`, ask a question with two parts, such as one that compares two books. The panel shows the sub-questions and which one found each passage.

**API**

The pages are built on these routes, which you can also call with `curl`:

| Route | What |
|---|---|
| `POST /api/books`, `GET /api/books`, `DELETE /api/books/{id}`, `POST /api/books/{id}/retry` | Upload, list, delete and retry books. The list has each book's index configuration and enrichment cost. |
| `POST /api/books/{id}/reindex`, `POST /api/books/reindex-out-of-date` | Reindex, when `LIBRAG_REINDEX_ENABLED` is on. |
| `POST /api/rag/search` | Search without an LLM answer. The body overrides the retrieval settings for one request, which makes it the quickest way to try values (see below). |
| `POST /api/chat`, `POST /api/chat/stream` | Ask a question, in one response or as server-sent events. |
| `GET /api/config/models` | The chat models and the default one. |

```bash
curl -s localhost:8000/api/rag/search -H 'content-type: application/json' \
  -d '{"query": "Who is Mr. Darcy?", "top_k": 5, "fusion_k": 50, "rerank": false}'
```

The search body takes `query`, and optionally `top_k`, `dense_k`, `bm25_k`, `fusion_k` (each 1 to 100), `token_budget` (100 to 32000), `rerank` (default `true`), `book_ids`, `authors`, `decompose` (default `false`) and `model`, the chat model that splits the question when `decompose` is `true`. Search with `decompose` makes one LLM call.

## Scripts

Each script runs on your machine, never in CI, and the ones that call providers stop at a cost cap.

| Script | What | Costs | More |
|---|---|---|---|
| `scripts/e2e-live` | The e2e suite against the real providers, on its own stack (`librag-live`, port 8100) that it removes afterwards. Needs both keys in the shell. | Stops at `LIBRAG_LIVE_BUDGET_USD`, default $2. A run cost about 3 cents. | [live-run.md](live-run.md) |
| `scripts/eval-fetch-books` | Downloads the 4 evaluation books into `eval/books/` and indexes them on the running stack. | About 2 cents of embeddings. | [evaluation.md](evaluation.md) |
| `scripts/eval-retrieval` | Recall@5/10/20 and MRR per search stage, on the running stack. Writes `eval-reports/retrieval-<timestamp>.json`. `--keep-books` keeps the books for the next run. | Embeddings of the books, unless they are kept. | [evaluation.md](evaluation.md) |
| `scripts/eval-retrieval --decompose [--model <id>]` | The same, with each question split into sub-questions first. | One LLM call per question. | [decomposition.md](decomposition.md#measure-it) |
| `scripts/eval-answers run [--ragas] [--keep-books]` | Asks every question on each chat model and writes `eval-reports/answers-<timestamp>.json`. `--ragas` adds Ragas scores, judged by GPT 6.1 Terra. Needs the keys in the shell. | 50 chat requests for 2 models; up to 5 more calls per answer with `--ragas`. Stops at `LIBRAG_LIVE_BUDGET_USD`. | [answer-evaluation.md](answer-evaluation.md) |
| `scripts/eval-answers grade [report]` | Serves a page on <http://127.0.0.1:8010> to grade the answers. | None. | [answer-evaluation.md](answer-evaluation.md#grade) |
| `scripts/eval-answers summary [report]` | Compares the models by grade and Ragas score. | None. | [answer-evaluation.md](answer-evaluation.md#summary) |

The eval scripts use the stack at `LIBRAG_EVAL_URL` (default `http://localhost:8000`), search only the evaluation books, and delete the books they uploaded unless you give `--keep-books`. To compare a setting, run the same script before and after the change, on the same library: [enrichment.md](enrichment.md#measure-it) and [decomposition.md](decomposition.md#measure-it) give the steps.

## Settings

The api, the worker and `migrate` read these variables. Set them in `.env` or the shell. An invalid value, such as `LIBRAG_DECOMPOSE=maybe` or `LIBRAG_SEARCH_TOP_K=500`, stops the app at startup with a message that names the variable. Switches take `on` or `off` (also `true`/`false` and `1`/`0`).

### Feature switches

| Variable | Default | What |
|---|---|---|
| `LIBRAG_AI_PROVIDERS` | `live` | `live` uses the real AI APIs. `fake` uses deterministic fakes and needs no keys. Compose sets `fake` only through `compose.test.yaml`. |
| `LIBRAG_REINDEX_ENABLED` | `off` | `on` adds Reindex and "Out of date" to the Library page and turns on the reindex routes; `off` hides them, and the routes answer 404. Retry and Delete are always on. |
| `LIBRAG_QUERY_REWRITE` | `on` | `on` lets the LLM rewrite a follow-up question into a standalone search query, with one extra LLM call per follow-up. `off` searches the question as asked. |
| `LIBRAG_DECOMPOSE` | `off` | `on` lets chat split a complex question into up to 4 sub-questions, each searched on its own and fused. One extra LLM call per question. Search does not read it; a search request asks with `"decompose": true`. See [decomposition.md](decomposition.md). |
| `LIBRAG_ENRICHMENT` | `off` | `on` makes the worker ask an LLM for a context line per passage, indexed with the passage. About 5 to 20 cents per novel with Haiku, and slower indexing. Changing it marks the indexed books out of date. See [enrichment.md](enrichment.md). |

Reranking has no switch: chat always reranks the fused candidates. A search request can leave it out with `"rerank": false`, which the retrieval evaluation uses to report fusion and rerank side by side.

### Models

| Variable | Default | What |
|---|---|---|
| `LIBRAG_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | The LiteLLM model that embeds passages and queries in live mode. Needs its provider's key. Each model has its own Qdrant collection, so a change marks the indexed books out of date; reindex them to search them with the new model. |
| `LIBRAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | The sentence-transformers CrossEncoder that reranks in live mode. The Docker image has only the default baked in; another model downloads from Hugging Face on the first search. |
| `LIBRAG_CHAT_MODELS` | `anthropic/claude-sonnet-5-5=Claude Sonnet 5.5,openai/gpt-6.1-terra=GPT 6.1 Terra` | The LiteLLM models chat can answer with, as comma-separated `<id>=<name>` entries. An entry without `=<name>` shows its ID. Each needs its provider's key. |
| `LIBRAG_CHAT_DEFAULT_MODEL` | the first chat model | The model a chat request gets when it names none. Must be one of `LIBRAG_CHAT_MODELS`. |
| `LIBRAG_ENRICHMENT_MODEL` | `anthropic/claude-haiku-5-5` | The LiteLLM model that writes the context lines when `LIBRAG_ENRICHMENT` is on. |

The query rewrite and the decomposition use the model that the chat request picked.

### Indexing

A change to these marks the indexed books out of date, with the reason on the Library page. Reindex parses the EPUB again; it needs `LIBRAG_REINDEX_ENABLED=on`.

| Variable | Default | What |
|---|---|---|
| `LIBRAG_PASSAGE_TARGET_TOKENS` | `350` | The size that the passages of a book are cut to, in tokens. Smaller passages match narrower questions; larger ones carry more context into each search hit. |
| `LIBRAG_PASSAGE_OVERLAP_TOKENS` | `50` | How many tokens each passage repeats from the one before it, from 0. Overlap keeps a sentence at a boundary findable in both passages. |
| `LIBRAG_MAX_UPLOAD_MB` | `50` | The largest EPUB that an upload accepts. It does not mark books out of date. |

### Retrieval

Search runs dense (embeddings) and BM25 (words) in Qdrant, fuses the two lists with reciprocal rank fusion, reranks the fused candidates with the CrossEncoder, and fills the context with the best passages up to the token budget. A search request can override each of these for one request, as above.

| Variable | Default | Range | What |
|---|---|---|---|
| `LIBRAG_DENSE_TOP_K` | `30` | 1 to 100 | How many passages the dense stage keeps. |
| `LIBRAG_BM25_TOP_K` | `30` | 1 to 100 | How many passages the BM25 stage keeps. |
| `LIBRAG_FUSION_TOP_K` | `30` | 1 to 100 | How many fused candidates the reranker scores. More candidates can raise recall, at the cost of rerank time. |
| `LIBRAG_SEARCH_TOP_K` | `10` | 1 to 100 | How many passages search returns, and chat can send to the LLM. |
| `LIBRAG_CONTEXT_TOKEN_BUDGET` | `4000` | 100 to 32000 | The most tokens that the returned passages hold together. It caps the LLM input per answer, and so the cost. |

The first real retrieval evaluation found that the rerank stage lowers Recall@10 compared with fusion (0.45 against 0.58). Compare both rows of `scripts/eval-retrieval` before you tune the rerank candidates.

### Where things run

| Variable | Default | What |
|---|---|---|
| `LIBRAG_PORT`, `LIBRAG_QDRANT_PORT` | `8000`, `6333` | The ports that Compose publishes on your machine. |
| `LIBRAG_QDRANT_URL` | `http://localhost:6333` | Qdrant's HTTP URL. Compose sets it for the containers. |
| `LIBRAG_DATABASE_URL` | `sqlite:///data/librag.db` | The SQLAlchemy URL of the metadata database. Compose sets it for the containers. |
| `LIBRAG_FILE_STORE_DIR` | `data/files` | The folder for uploaded EPUB files. Compose sets it for the containers. |
| `LIBRAG_QDRANT_COLLECTION_PREFIX` | `passages` | Each embedding model gets the Qdrant collection `<prefix>_<model>`, such as `passages_openai_text-embedding-3-small`. |

### Scripts

| Variable | Default | What |
|---|---|---|
| `LIBRAG_LIVE_BUDGET_USD` | `2` | The cost cap of `scripts/e2e-live` and `scripts/eval-answers run`, in dollars. |
| `LIBRAG_LIVE_PORT`, `LIBRAG_LIVE_QDRANT_PORT` | `8100`, `6433` | The ports of the `librag-live` stack that `scripts/e2e-live` starts. |
| `LIBRAG_EVAL_URL` | `http://localhost:8000` | The stack that the eval scripts use. |
| `LIBRAG_E2E_URL` | `http://localhost:8000` | The stack that `pytest tests/e2e` tests. |
