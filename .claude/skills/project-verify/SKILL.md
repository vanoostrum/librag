---
name: project-verify
description: How to install, run, lint, type-check, and test the LibRag FastAPI app. Use before every commit, and to reproduce CI failures.
---

# project-verify

## Install

```bash
uv sync
```

## Verify (same as CI)

Run all four; all must pass.

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Fix formatting with `uv run ruff format .` and safe lint fixes with `uv run ruff check --fix .`.

## Run the app

```bash
uv run fastapi dev src/librag/main.py
```

## Notes

- Ruff runs with `select = ["ALL"]`. Fix the code rather than adding ignores. If an ignore is truly needed, scope it to one line with a reason.
- Follow the test seam rule in `CLAUDE.md`. A new route needs a test in `tests/integration/`, which uses `TestClient`. Add a test in `tests/unit/` only when the rule allows it.
- `uv run pytest` prints line and branch coverage for `src/librag/`. Lines and branches under `Missing` have no test.
- `tests/integration/test_routes.py` asserts the exact list of routes. Update it when adding a route.
- Add dependencies with `uv add <pkg>` (or `uv add --dev <pkg>`) and commit `uv.lock`.
