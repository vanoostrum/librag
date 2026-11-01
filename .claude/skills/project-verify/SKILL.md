---
name: project-verify
description: How to install, run, lint, type-check, and test the LibRag FastAPI app. Use before every commit, and to reproduce CI failures.
---

# project-verify

## Install

```bash
uv sync
```

## Qdrant for the tests

The route tests for `/health` use a real Qdrant. They read its URL from `LIBRAG_QDRANT_URL`, with the default `http://localhost:6333`. When Qdrant is not ready, they fail with a message that says how to start it. They never skip.

- **With Docker:** run `docker compose up -d --wait qdrant`. It publishes Qdrant on `127.0.0.1:6333`.
- **Without Docker, or when Docker cannot pull images** (the cloud sandbox): start the verify skill's process mode with `$V launch`. Then run `export LIBRAG_QDRANT_URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/qdrant-port)`. Run `$V cleanup` when you are done.
- **In CI:** the `checks` job runs Qdrant as a service container on `localhost:6333`.

Each test gets its own SQLite database and file store in a temporary folder, migrated with Alembic. Tests that index books write to Qdrant collections under a prefix of their own (`test_<random>_fake`), and delete them afterwards. Fixture EPUBs are written by `tests/epubs.py`; the repo holds no binary EPUBs.

## The tokenizer file

Passages are counted with tiktoken `cl100k_base`. tiktoken downloads its file from `openaipublic.blob.core.windows.net` on first use, and caches it in `TIKTOKEN_CACHE_DIR` (default: the system temp folder). CI downloads it; the Docker image bakes it in at build time.

The cloud sandbox blocks that host. There, put a copy of the file in a cache folder and export `TIKTOKEN_CACHE_DIR` before running pytest or `$V launch`. The file name is the SHA-1 of the download URL. tiktoken checks the file's SHA-256 (`223921b7…65b2a7`) and refuses a wrong file.

```bash
export TIKTOKEN_CACHE_DIR=/tmp/tiktoken-cache && mkdir -p $TIKTOKEN_CACHE_DIR
cp <copy of cl100k_base.tiktoken> $TIKTOKEN_CACHE_DIR/9b5ad71b2ce5302211f9c61530b329a4922fc6a4
```

## Verify (same as the `checks` CI job)

Run all four; all must pass.

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Fix formatting with `uv run ruff format .` and safe lint fixes with `uv run ruff check --fix .`.

## End-to-end tests

`tests/e2e/` runs against a running stack over HTTP, so `uv run pytest` does not collect it. The `e2e` CI job starts the stack with `compose.test.yaml` and runs it. Run it locally against any running stack:

```bash
LIBRAG_E2E_URL=http://127.0.0.1:<port> uv run pytest tests/e2e --no-cov
```

## Run the app

Use the verify skill (`$V launch`), or the commands in `README.md`. The app needs Qdrant, a migrated database and the worker before `/health` returns 200.

## Notes

- Ruff runs with `select = ["ALL"]`. Fix the code rather than adding ignores. If an ignore is truly needed, scope it to one line with a reason.
- Follow the test seam rule in `CLAUDE.md`. A new route needs a test in `tests/integration/`, which uses `TestClient`. Add a test in `tests/unit/` only when the rule allows it.
- `uv run pytest` prints line and branch coverage for `src/librag/`, also for the worker process that a test starts. Lines and branches under `Missing` have no test.
- Change the schema only with a new Alembic migration in `src/librag/migrations/versions/`.
- `tests/integration/test_routes.py` asserts the exact list of routes. Update it when adding a route.
- Add dependencies with `uv add <pkg>` (or `uv add --dev <pkg>`) and commit `uv.lock`.
