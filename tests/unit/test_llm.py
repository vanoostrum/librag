# Copyright (C) 2026 Theo van Oostrum
"""The LiteLLM chat client: what it reads from LiteLLM, which no fake route shows.

LiteLLM's `mock_response` builds a real response without a network call.
"""

import functools
from collections.abc import Callable, Generator, Iterator
from types import SimpleNamespace

import litellm
import pytest

from librag.llm import Completion, FakeLlm, LiteLlm, LlmError, make_llm
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


def test_live_llm_streams_the_reply_then_its_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The streamed reply comes in pieces, then one completion with tokens and cost."""
    mock_completion(monkeypatch, '{"parts": [{"kind": "general", "text": "Known."}]}')
    *pieces, completion = LiteLlm().stream("anthropic/claude-sonnet-5-5", PROMPT)
    assert all(isinstance(piece, str) for piece in pieces)
    assert isinstance(completion, Completion)
    assert "".join(str(piece) for piece in pieces) == completion.text
    assert completion.text.startswith('{"parts"')
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0
    assert completion.cost_usd is not None


def test_live_llm_stream_raises_the_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider error while streaming becomes LlmError, with its message."""
    mock_completion(monkeypatch, Exception("the API is overloaded"))
    with pytest.raises(LlmError, match="the API is overloaded"):
        list(LiteLlm().stream("anthropic/claude-sonnet-5-5", PROMPT))


class ProviderStream:
    """The provider's HTTP stream: chunks of one word, and whether it was closed."""

    def __init__(self) -> None:
        """Start unread and open."""
        self.read = 0
        self.closed = False

    def chunks(self) -> Generator[SimpleNamespace]:
        """Yield chunks in the shape LiteLLM gives them, until closed."""
        try:
            while True:
                self.read += 1
                delta = SimpleNamespace(content=f"word{self.read} ")
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
        finally:
            self.closed = True


class StreamWrapper:
    """LiteLLM's stream wrapper: it reads the provider's stream, but has no close."""

    def __init__(self, completion_stream: object, chunks: Iterator[object]) -> None:
        """Wrap `completion_stream`, which reads `chunks`."""
        self.completion_stream = completion_stream
        self._chunks = chunks

    def __iter__(self) -> Iterator[object]:
        """Yield the provider's chunks."""
        return self._chunks


def openai_shape(provider: ProviderStream) -> StreamWrapper:
    """OpenAI: the wrapped stream is the SDK's stream, which has `close`."""
    chunks = provider.chunks()
    return StreamWrapper(SimpleNamespace(close=chunks.close), chunks)


def anthropic_shape(provider: ProviderStream) -> StreamWrapper:
    """Anthropic: the wrapped stream holds the HTTP lines as `streaming_response`."""
    chunks = provider.chunks()
    return StreamWrapper(SimpleNamespace(streaming_response=chunks), chunks)


@pytest.mark.parametrize("shape", [openai_shape, anthropic_shape])
def test_closing_the_stream_closes_the_provider_stream(
    monkeypatch: pytest.MonkeyPatch,
    shape: Callable[[ProviderStream], StreamWrapper],
) -> None:
    """A stream that the caller stops closes the provider's HTTP stream.

    The provider then stops writing, and stops charging for output.
    """
    provider = ProviderStream()
    # Others, such as LiteLLM's callbacks, can hold the wrapper, so it is not
    # collected (and so closed) when the stream ends.
    wrapper = shape(provider)
    monkeypatch.setattr(litellm, "completion", lambda **_: wrapper)
    stream = LiteLlm().stream("anthropic/claude-sonnet-5-5", PROMPT)
    assert [next(stream), next(stream)] == ["word1 ", "word2 "]
    stream.close()
    assert provider.closed
    assert provider.read == 2  # noqa: PLR2004


def test_live_llm_estimates_a_stopped_reply() -> None:
    """A reply stopped halfway is counted with the model's tokenizer and priced."""
    estimate = LiteLlm().estimate(
        "anthropic/claude-sonnet-5-5", PROMPT, '{"parts": [{"kind": "book",'
    )
    assert estimate.input_tokens > 0
    assert estimate.output_tokens > 0
    assert estimate.cost_usd is not None
    assert estimate.cost_usd > 0


def test_live_llm_estimate_without_a_price_has_no_cost() -> None:
    """For a model that LiteLLM has no price for, the estimated cost is None."""
    estimate = LiteLlm().estimate("openai/no-such-chat-model", PROMPT, "Some text")
    assert estimate.input_tokens > 0
    assert estimate.output_tokens > 0
    assert estimate.cost_usd is None


def test_provider_error_midway_closes_the_provider_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that fails halfway raises LlmError, and its stream is closed."""
    provider = ProviderStream()
    chunks = provider.chunks()

    def failing() -> Iterator[object]:
        yield next(chunks)
        msg = "connection reset"
        raise ConnectionError(msg)

    wrapper = StreamWrapper(SimpleNamespace(close=chunks.close), failing())
    monkeypatch.setattr(litellm, "completion", lambda **_: wrapper)
    stream = LiteLlm().stream("anthropic/claude-sonnet-5-5", PROMPT)
    assert next(stream) == "word1 "
    with pytest.raises(LlmError, match="connection reset"):
        next(stream)
    assert provider.closed
