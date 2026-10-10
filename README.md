# librag

## Development

Install the app and its dev tools:

```bash
uv sync
```

Run the app locally:

```bash
uv run fastapi dev src/librag/main.py
```

Lint and format-check:

```bash
uv run ruff check .
uv run ruff format --check .
```

Type-check:

```bash
uv run mypy src tests
```

Test:

```bash
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest
```

