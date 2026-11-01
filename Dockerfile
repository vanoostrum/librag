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

# Dependencies first, so a code change does not rebuild this layer. The `rerank`
# extra brings sentence-transformers and CPU-only PyTorch for the live reranker.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra rerank --no-install-project

# Bake in the reranker model, so the running stack never fetches it. Its name is
# also the default of LIBRAG_RERANKER_MODEL in the image.
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENV HF_HOME=/app/hf-cache \
    LIBRAG_RERANKER_MODEL=${RERANKER_MODEL}
RUN python -c "import sys; from sentence_transformers import CrossEncoder; CrossEncoder(sys.argv[1])" "$RERANKER_MODEL"
ENV HF_HUB_OFFLINE=1

COPY README.md alembic.ini ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra rerank --no-editable

# Bake in the tokenizer file, so the worker never downloads it at run time.
ENV TIKTOKEN_CACHE_DIR=/app/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

RUN useradd --system --uid 1000 librag && mkdir -p /data && chown librag /data
USER librag
EXPOSE 8000
CMD ["uvicorn", "librag.main:app", "--host", "0.0.0.0", "--port", "8000"]
