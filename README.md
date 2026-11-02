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

Set `LIBRAG_PORT` or `LIBRAG_QDRANT_PORT` to publish on other ports. The live providers need API keys in `.env`; see [Manual testing and settings](#manual-testing-and-settings).

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

`scripts/eval-retrieval` measures retrieval on 4 Project Gutenberg books: Recall@5/10/20 and MRR for each search stage. See [docs/evaluation.md](docs/evaluation.md). [docs/enrichment.md](docs/enrichment.md) says how to measure contextual enrichment with it, and [docs/decomposition.md](docs/decomposition.md) how to measure question decomposition.

`scripts/eval-answers` asks the same questions through chat on each model, serves a local page to grade the answers, and summarizes the grades and the opt-in Ragas scores. See [docs/answer-evaluation.md](docs/answer-evaluation.md).

## Manual testing and settings

[docs/manual-testing.md](docs/manual-testing.md) says how to try the app by hand, what each script measures and costs, and every setting: the feature switches (`LIBRAG_REINDEX_ENABLED`, `LIBRAG_QUERY_REWRITE`, `LIBRAG_DECOMPOSE`, `LIBRAG_ENRICHMENT`), the models, and the indexing and retrieval values to tune.

Put your API keys and settings in `.env` in the repo root, which git ignores. Compose passes them to the stack:

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and ANTHROPIC_API_KEY
docker compose up -d --build --wait
```

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
