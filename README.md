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

## Settings

The api, the worker and `migrate` read these environment variables:

| Variable | Default | What |
|---|---|---|
| `LIBRAG_QDRANT_URL` | `http://localhost:6333` | Qdrant HTTP URL. |
| `LIBRAG_DATABASE_URL` | `sqlite:///data/librag.db` | SQLAlchemy URL of the metadata database. |
| `LIBRAG_FILE_STORE_DIR` | `data/files` | Folder for uploaded EPUB files. |
| `LIBRAG_AI_PROVIDERS` | `live` | `live` uses the real AI APIs. `fake` uses deterministic fakes. Any other value stops the app at startup. |

## Development

Install the app and its dev tools:

```bash
uv sync
```

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
