# Copyright (C) 2026 Theo van Oostrum
"""The LiteLLM chat client: what it reads from LiteLLM, which no fake route shows.

LiteLLM's `mock_response` builds a real response without a network call.
"""

import functools

import litellm
import pytest

from librag.llm import FakeLlm, LiteLlm, LlmError, make_llm
from librag.prompts import AnswerPrompt
from librag.settings import Settings

PROMPT = AnswerPrompt("Who kept the lighthouse?", [])


def mock_completion(monkeypatch: pytest.MonkeyPatch, response: object) -> None:
    """Make `litellm.completion` answer with `response`, offline."""
    monkeypatch.setattr(
        litellm,
        "completion",
        functools.partial(litellm.completion, mock_response=response),
    )


def test_live_llm_reads_litellm_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The LiteLLM client returns the reply, the tokens and LiteLLM's cost."""
    mock_completion(monkeypatch, '{"parts": []}')
    completion = LiteLlm().complete("anthropic/claude-sonnet-5-5", PROMPT)
    assert completion.text == '{"parts": []}'
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0
    assert completion.cost_usd is not None
    assert completion.cost_usd > 0


def test_live_llm_without_a_price_has_no_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """For a model that LiteLLM has no price for, the cost is None, not 0."""
    mock_completion(monkeypatch, '{"parts": []}')
    completion = LiteLlm().complete("openai/no-such-chat-model", PROMPT)
    assert completion.cost_usd is None


def test_model_missing_from_the_price_table_has_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that LiteLLM routes but cannot price costs None, not 0.

    LiteLLM's own cost function returns 0 for some of those models.
    """
    mock_completion(monkeypatch, '{"parts": []}')
    prices = {k: v for k, v in litellm.model_cost.items() if k != "gpt-6.1-terra"}
    monkeypatch.setattr(litellm, "model_cost", prices)
    completion = LiteLlm().complete("openai/gpt-6.1-terra", PROMPT)
    assert completion.cost_usd is None


def test_live_llm_raises_the_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider error becomes LlmError, with the provider's message."""
    mock_completion(monkeypatch, Exception("the API is overloaded"))
    with pytest.raises(LlmError, match="the API is overloaded"):
        LiteLlm().complete("anthropic/claude-sonnet-5-5", PROMPT)


def test_settings_pick_the_llm() -> None:
    """`fake` picks the fake LLM; `live` picks LiteLLM."""
    assert isinstance(make_llm(Settings(ai_providers="fake")), FakeLlm)
    assert isinstance(make_llm(Settings()), LiteLlm)
