# librag

## Run the stack

Start LibRag with Qdrant and the worker:

```bash
docker compose up -d --build --wait
```

The command exits when every service is healthy. The app is then at <http://localhost:8000>. `GET /health` returns 200 when Qdrant, the metadata database and the worker are ready.

The stack has four services:

- `qdrant` is the vector database, on `127.0.0.1:6333`.
- `migrate` runs `alembic upgrade head` once, then exits.
- `api` serves the app on port 8000.
- `worker` runs background work. For now it only writes a heartbeat.

The metadata database (SQLite) and the file store share the `librag-data` volume. Qdrant keeps its data in the `qdrant-data` volume.

Stop the stack with `docker compose down`. Add `-v` to also delete the data.

Set `LIBRAG_PORT` or `LIBRAG_QDRANT_PORT` to publish on other ports.

### Prerequisites

- Docker with the Compose plugin, version 2.20 or later.
- About 2 GB of free disk for the images, and 1 GB of free memory.
- Network access to Docker Hub and ghcr.io for the first build.

### Test stack

The test overlay selects the fake AI providers, so it needs no API keys:

```bash
docker compose -f compose.yaml -f compose.test.yaml up -d --build --wait
uv run pytest tests/e2e --no-cov
docker compose -f compose.yaml -f compose.test.yaml down -v
```

### Live run

`scripts/e2e-live` runs the same suite against the real AI providers, with your own `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. It stops at a cost cap of $2, which `LIBRAG_LIVE_BUDGET_USD` changes. See [docs/live-run.md](docs/live-run.md).

## Settings

The api, the worker and `migrate` read these environment variables:

| Variable | Default | What |
|---|---|---|
| `LIBRAG_QDRANT_URL` | `http://localhost:6333` | Qdrant HTTP URL. |
| `LIBRAG_DATABASE_URL` | `sqlite:///data/librag.db` | SQLAlchemy URL of the metadata database. |
| `LIBRAG_FILE_STORE_DIR` | `data/files` | Folder for uploaded EPUB files. |
| `LIBRAG_AI_PROVIDERS` | `live` | `live` uses the real AI APIs. `fake` uses deterministic fakes. Any other value stops the app at startup. |
| `LIBRAG_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | The LiteLLM model that embeds passages in `live` mode. It also needs that provider's key, such as `OPENAI_API_KEY`. |
| `LIBRAG_QDRANT_COLLECTION_PREFIX` | `passages` | Each embedding model gets the Qdrant collection `<prefix>_<model>`, such as `passages_openai_text-embedding-3-small` or `passages_fake`. |
| `LIBRAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | The sentence-transformers CrossEncoder that reranks search results in `live` mode. The Docker image has this model baked in. |
| `LIBRAG_SEARCH_TOP_K`, `LIBRAG_DENSE_TOP_K`, `LIBRAG_BM25_TOP_K`, `LIBRAG_FUSION_TOP_K` | `10`, `30`, `30`, `30` | How many passages search returns, and how many the dense, BM25 and fusion stages keep. Each is 1 to 100. |
| `LIBRAG_CONTEXT_TOKEN_BUDGET` | `4000` | The most tokens that search's results hold together, from 100 to 32000. |
| `LIBRAG_CHAT_MODELS` | `anthropic/claude-sonnet-5-5=Claude Sonnet 5.5,openai/gpt-6.1-terra=GPT 6.1 Terra` | The LiteLLM models that chat can answer with, as comma-separated `<id>=<name>` entries. In `live` mode each needs its provider's key, such as `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. |
| `LIBRAG_CHAT_DEFAULT_MODEL` | the first chat model | The model a chat request gets when it names none. It must be one of `LIBRAG_CHAT_MODELS`. |
| `LIBRAG_QUERY_REWRITE` | `on` | `on` lets the LLM rewrite a follow-up question into a standalone search query; `off` searches the question as asked. |
| `LIBRAG_REINDEX_ENABLED` | `off` | `on` adds Reindex to the Library page and turns on `POST /api/books/{id}/reindex` and `POST /api/books/reindex-out-of-date`; `off` hides them, and the routes answer 404. Retry and Delete are always on. |

## Development

Install the app and its dev tools:

```bash
uv sync
```

This leaves out the live reranker (sentence-transformers and CPU-only PyTorch), so `live` mode cannot rerank. Add it with `uv sync --extra rerank`; the first search then downloads the reranker model from Hugging Face. `LIBRAG_AI_PROVIDERS=fake` needs neither.

The tests need a running Qdrant. Start the one from the stack:

```bash
docker compose up -d --wait qdrant
```

Run the app locally, against that Qdrant:

```bash
mkdir -p data
uv run alembic upgrade head
uv run fastapi dev src/librag/main.py
uv run python -m librag.worker
```

Run the worker in a second terminal. Without it, `/health` returns 503.

Lint and format-check:

```bash
uv run ruff check .
uv run ruff format --check .
```

Type-check:

```bash
uv run ty check
```

Test:

```bash
uv run pytest
```
