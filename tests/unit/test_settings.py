# Copyright (C) 2026 Theo van Oostrum
"""An invalid setting stops LibRag from starting. No request can reach that case."""

import pytest
from fastapi.testclient import TestClient

from librag.main import create_app
from librag.settings import ChatModel, Settings, SettingsError


def test_invalid_ai_providers_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app does not start when LIBRAG_AI_PROVIDERS is not live or fake."""
    monkeypatch.setenv("LIBRAG_AI_PROVIDERS", "mock")
    with (
        pytest.raises(SettingsError, match="LIBRAG_AI_PROVIDERS") as error,
        TestClient(create_app()),
    ):
        pass
    assert "'mock'" in str(error.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LIBRAG_PASSAGE_TARGET_TOKENS", "0"),
        ("LIBRAG_PASSAGE_TARGET_TOKENS", "many"),
        ("LIBRAG_PASSAGE_OVERLAP_TOKENS", "-1"),
        ("LIBRAG_MAX_UPLOAD_MB", "1.5"),
        ("LIBRAG_SEARCH_TOP_K", "0"),
        ("LIBRAG_DENSE_TOP_K", "101"),
        ("LIBRAG_BM25_TOP_K", "lots"),
        ("LIBRAG_FUSION_TOP_K", "101"),
        ("LIBRAG_CONTEXT_TOKEN_BUDGET", "99"),
        ("LIBRAG_CONTEXT_TOKEN_BUDGET", "32001"),
    ],
)
def test_invalid_number_stops_startup(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """The app does not start when a size setting is not a whole number in range."""
    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError, match=name) as error, TestClient(create_app()):
        pass
    assert repr(value) in str(error.value)


def test_size_settings_are_read_from_the_environment() -> None:
    """The passage and upload sizes come from their LIBRAG_* variables."""
    settings = Settings.from_env(
        {
            "LIBRAG_PASSAGE_TARGET_TOKENS": "200",
            "LIBRAG_PASSAGE_OVERLAP_TOKENS": "0",
            "LIBRAG_MAX_UPLOAD_MB": "5",
        }
    )
    assert (
        settings.passage_target_tokens,
        settings.passage_overlap_tokens,
        settings.max_upload_mb,
    ) == (200, 0, 5)
    assert (Settings().passage_target_tokens, Settings().max_upload_mb) == (350, 50)


def test_embedding_settings_are_read_from_the_environment() -> None:
    """The embedding model and the collection prefix come from LIBRAG_* variables."""
    settings = Settings.from_env(
        {
            "LIBRAG_EMBEDDING_MODEL": "openai/text-embedding-3-large",
            "LIBRAG_QDRANT_COLLECTION_PREFIX": "staging",
        }
    )
    assert (settings.embedding_model, settings.qdrant_collection_prefix) == (
        "openai/text-embedding-3-large",
        "staging",
    )
    assert (Settings().embedding_model, Settings().qdrant_collection_prefix) == (
        "openai/text-embedding-3-small",
        "passages",
    )


def test_search_settings_are_read_from_the_environment() -> None:
    """Search's top-k values come from LIBRAG_* variables, 1 to 100."""
    settings = Settings.from_env(
        {
            "LIBRAG_SEARCH_TOP_K": "1",
            "LIBRAG_DENSE_TOP_K": "100",
            "LIBRAG_BM25_TOP_K": "50",
        }
    )
    assert (settings.search_top_k, settings.dense_top_k, settings.bm25_top_k) == (
        1,
        100,
        50,
    )


def test_rerank_settings_are_read_from_the_environment() -> None:
    """The reranker model, fusion_k and the context budget come from LIBRAG_*."""
    settings = Settings.from_env(
        {
            "LIBRAG_RERANKER_MODEL": "cross-encoder/ms-marco-MiniLM-L-12-v2",
            "LIBRAG_FUSION_TOP_K": "100",
            "LIBRAG_CONTEXT_TOKEN_BUDGET": "100",
        }
    )
    assert (
        settings.reranker_model,
        settings.fusion_top_k,
        settings.context_token_budget,
    ) == ("cross-encoder/ms-marco-MiniLM-L-12-v2", 100, 100)
    assert (
        Settings().reranker_model,
        Settings().fusion_top_k,
        Settings().context_token_budget,
    ) == ("cross-encoder/ms-marco-MiniLM-L-6-v2", 30, 4000)
    largest = Settings.from_env({"LIBRAG_CONTEXT_TOKEN_BUDGET": "32000"})
    assert largest.context_token_budget == 32000  # noqa: PLR2004


@pytest.mark.parametrize(
    ("env", "name", "value"),
    [
        (
            {"LIBRAG_CHAT_DEFAULT_MODEL": "openai/gpt-4"},
            "LIBRAG_CHAT_DEFAULT_MODEL",
            "openai/gpt-4",
        ),
        (
            {"LIBRAG_CHAT_MODELS": "a/one=One,,b/two"},
            "LIBRAG_CHAT_MODELS",
            "a/one=One,,b/two",
        ),
        ({"LIBRAG_QUERY_REWRITE": "sometimes"}, "LIBRAG_QUERY_REWRITE", "sometimes"),
    ],
)
def test_invalid_chat_setting_stops_startup(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], name: str, value: str
) -> None:
    """The app does not start with a chat setting that it cannot use."""
    for key, raw in env.items():
        monkeypatch.setenv(key, raw)
    with pytest.raises(SettingsError, match=name) as error, TestClient(create_app()):
        pass
    assert repr(value) in str(error.value)


def test_chat_settings_are_read_from_the_environment() -> None:
    """The chat models, the default and the rewrite switch come from LIBRAG_*."""
    settings = Settings.from_env(
        {
            "LIBRAG_CHAT_MODELS": "openai/gpt-6.1-terra=GPT 6.1 Terra, gemini/flash",
            "LIBRAG_CHAT_DEFAULT_MODEL": "gemini/flash",
            "LIBRAG_QUERY_REWRITE": "Off",
        }
    )
    assert settings.chat_models == (
        ChatModel("openai/gpt-6.1-terra", "GPT 6.1 Terra"),
        ChatModel("gemini/flash", "gemini/flash"),
    )
    assert settings.chat_default_model == "gemini/flash"
    assert settings.query_rewrite is False


def test_default_chat_model_is_the_first_configured() -> None:
    """Without LIBRAG_CHAT_DEFAULT_MODEL, the first model is the default."""
    settings = Settings.from_env({"LIBRAG_CHAT_MODELS": "b/two=Two,a/one=One"})
    assert settings.chat_default_model == "b/two"
    assert Settings.from_env({}).chat_default_model == "anthropic/claude-sonnet-5-5"
    assert Settings.from_env({"LIBRAG_QUERY_REWRITE": "1"}).query_rewrite is True
