# One image for the api, the worker and the migrate step. compose.yaml picks the command.
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so a code change does not rebuild this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY README.md alembic.ini ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Bake in the tokenizer file, so the worker never downloads it at run time.
ENV TIKTOKEN_CACHE_DIR=/app/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

RUN useradd --system --uid 1000 librag && mkdir -p /data && chown librag /data
USER librag
EXPOSE 8000
CMD ["uvicorn", "librag.main:app", "--host", "0.0.0.0", "--port", "8000"]
