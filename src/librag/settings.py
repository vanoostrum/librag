# Copyright (C) 2026 Theo van Oostrum
"""Settings that the api and the worker read from `LIBRAG_*` environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

AiProviders = Literal["live", "fake"]
AI_PROVIDERS_VALUES: tuple[AiProviders, ...] = ("live", "fake")
# Search returns, and each retrieval stage keeps, at most this many passages.
MAX_SEARCH_K = 100
# The context that search selects holds this many tokens, at least and at most.
MIN_TOKEN_BUDGET = 100
MAX_TOKEN_BUDGET = 32000


@dataclass(frozen=True)
class ChatModel:
    """A model that chat can answer with: its LiteLLM ID and the name people see."""

    id: str
    name: str


DEFAULT_CHAT_MODELS = (
    ChatModel("anthropic/claude-sonnet-5-5", "Claude Sonnet 5.5"),
    ChatModel("openai/gpt-6.1-terra", "GPT 6.1 Terra"),
)
_SWITCH_VALUES = {
    "on": True,
    "true": True,
    "1": True,
    "off": False,
    "false": False,
    "0": False,
}


class SettingsError(ValueError):
    """A `LIBRAG_*` environment variable has a value that LibRag cannot use."""


@dataclass(frozen=True)
class Settings:
    """Where LibRag finds Qdrant, its metadata database and its file store."""

    qdrant_url: str = "http://localhost:6333"
    database_url: str = "sqlite:///data/librag.db"
    file_store_dir: str = "data/files"
    ai_providers: AiProviders = "live"
    embedding_model: str = "openai/text-embedding-3-small"
    # Each embedding model gets the collection `<prefix>_<model slug>`.
    qdrant_collection_prefix: str = "passages"
    passage_target_tokens: int = 350
    passage_overlap_tokens: int = 50
    max_upload_mb: int = 50
    # How many passages search returns, and how many each retrieval stage keeps.
    search_top_k: int = 10
    dense_top_k: int = 30
    bm25_top_k: int = 30
    # How many fused candidates the reranker scores, and the context's token budget.
    fusion_top_k: int = 30
    context_token_budget: int = 4000
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # The models a chat request can pick, and the one it gets without picking.
    chat_models: tuple[ChatModel, ...] = DEFAULT_CHAT_MODELS
    chat_default_model: str = DEFAULT_CHAT_MODELS[0].id
    # Rewrite a follow-up question into a standalone search query.
    query_rewrite: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Read the settings from the environment, with a default for each one."""
        env = os.environ if environ is None else environ
        defaults = cls()
        ai_providers = env.get("LIBRAG_AI_PROVIDERS", defaults.ai_providers)
        if ai_providers not in AI_PROVIDERS_VALUES:
            msg = f"LIBRAG_AI_PROVIDERS must be 'live' or 'fake', not {ai_providers!r}"
            raise SettingsError(msg)
        chat_models = _chat_models(env, defaults.chat_models)
        chat_default_model = env.get("LIBRAG_CHAT_DEFAULT_MODEL", chat_models[0].id)
        if chat_default_model not in {model.id for model in chat_models}:
            msg = (
                "LIBRAG_CHAT_DEFAULT_MODEL must be one of LIBRAG_CHAT_MODELS, "
                f"not {chat_default_model!r}"
            )
            raise SettingsError(msg)
        return cls(
            qdrant_url=env.get("LIBRAG_QDRANT_URL", defaults.qdrant_url),
            database_url=env.get("LIBRAG_DATABASE_URL", defaults.database_url),
            file_store_dir=env.get("LIBRAG_FILE_STORE_DIR", defaults.file_store_dir),
            ai_providers=ai_providers,
            embedding_model=env.get("LIBRAG_EMBEDDING_MODEL", defaults.embedding_model),
            qdrant_collection_prefix=env.get(
                "LIBRAG_QDRANT_COLLECTION_PREFIX", defaults.qdrant_collection_prefix
            ),
            passage_target_tokens=_positive_int(
                env, "LIBRAG_PASSAGE_TARGET_TOKENS", defaults.passage_target_tokens
            ),
            passage_overlap_tokens=_positive_int(
                env,
                "LIBRAG_PASSAGE_OVERLAP_TOKENS",
                defaults.passage_overlap_tokens,
                minimum=0,
            ),
            max_upload_mb=_positive_int(
                env, "LIBRAG_MAX_UPLOAD_MB", defaults.max_upload_mb
            ),
            search_top_k=_positive_int(
                env, "LIBRAG_SEARCH_TOP_K", defaults.search_top_k, maximum=MAX_SEARCH_K
            ),
            dense_top_k=_positive_int(
                env, "LIBRAG_DENSE_TOP_K", defaults.dense_top_k, maximum=MAX_SEARCH_K
            ),
            bm25_top_k=_positive_int(
                env, "LIBRAG_BM25_TOP_K", defaults.bm25_top_k, maximum=MAX_SEARCH_K
            ),
            fusion_top_k=_positive_int(
                env, "LIBRAG_FUSION_TOP_K", defaults.fusion_top_k, maximum=MAX_SEARCH_K
            ),
            context_token_budget=_positive_int(
                env,
                "LIBRAG_CONTEXT_TOKEN_BUDGET",
                defaults.context_token_budget,
                minimum=MIN_TOKEN_BUDGET,
                maximum=MAX_TOKEN_BUDGET,
            ),
            reranker_model=env.get("LIBRAG_RERANKER_MODEL", defaults.reranker_model),
            chat_models=chat_models,
            chat_default_model=chat_default_model,
            query_rewrite=_switch(env, "LIBRAG_QUERY_REWRITE", defaults.query_rewrite),
        )


def _chat_models(
    env: Mapping[str, str], default: tuple[ChatModel, ...]
) -> tuple[ChatModel, ...]:
    """Return the models in `LIBRAG_CHAT_MODELS`: `<id>=<name>`, comma-separated.

    A model without `=<name>` shows its ID as its name.
    """
    raw = env.get("LIBRAG_CHAT_MODELS")
    if raw is None:
        return default
    models: list[ChatModel] = []
    for entry in raw.split(","):
        model_id, _, name = (part.strip() for part in entry.partition("="))
        if not model_id:
            msg = f"LIBRAG_CHAT_MODELS must list '<id>=<name>' entries, not {raw!r}"
            raise SettingsError(msg)
        models.append(ChatModel(model_id, name or model_id))
    return tuple(models)


def _switch(env: Mapping[str, str], name: str, default: bool) -> bool:  # noqa: FBT001
    """Return the on or off value in `env[name]`."""
    raw = env.get(name)
    if raw is None:
        return default
    if raw.lower() not in _SWITCH_VALUES:
        msg = f"{name} must be on or off, not {raw!r}"
        raise SettingsError(msg)
    return _SWITCH_VALUES[raw.lower()]


def _positive_int(
    env: Mapping[str, str],
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """Return the whole number in `env[name]`, from `minimum` to `maximum`."""
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = minimum - 1
    if value < minimum:
        msg = f"{name} must be a whole number of at least {minimum}, not {raw!r}"
        raise SettingsError(msg)
    if maximum is not None and value > maximum:
        msg = f"{name} must be a whole number from {minimum} to {maximum}, not {raw!r}"
        raise SettingsError(msg)
    return value
