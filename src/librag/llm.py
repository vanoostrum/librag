# Copyright (C) 2026 Theo van Oostrum
"""Chat LLMs: LiteLLM, or an in-process fake (ADR 0005)."""

import json
import re
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Protocol

from librag.prompts import (
    MAX_SUBQUESTIONS,
    NO_PASSAGE,
    AnswerPrompt,
    DecomposePrompt,
    Prompt,
    RewritePrompt,
)
from librag.settings import Settings

WORD = re.compile(r"\w+")
MAX_OUTPUT_TOKENS = 4096
# The fake LLM streams its reply in chunks of this many characters.
FAKE_CHUNK = 16


@dataclass(frozen=True)
class Completion:
    """What the LLM wrote, and what it cost."""

    text: str
    input_tokens: int
    output_tokens: int
    # None when LiteLLM does not know the model's price.
    cost_usd: float | None


class LlmError(Exception):
    """The LLM provider refused or failed the request. The text is its message."""


class Llm(Protocol):
    """Completes a prompt with the model a chat request picked."""

    def complete(self, model: str, prompt: Prompt) -> Completion:
        """Return the model's reply to `prompt`, or raise `LlmError`."""
        ...

    def stream(self, model: str, prompt: Prompt) -> Generator[str | Completion]:
        """Yield the reply's text in pieces, then its `Completion`.

        Raise `LlmError` when the provider fails, also halfway. Closing the
        generator before the end stops the provider's stream.
        """
        ...

    def estimate(self, model: str, prompt: Prompt, text: str) -> Completion:
        """Return the estimated usage of a reply that stopped after `text`."""
        ...


def strip_fence(text: str) -> str:
    """Return `text` without a Markdown code fence around it."""
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3]
        text = text.removeprefix("json")
    return text.strip()


def _words(text: str) -> int:
    return len(WORD.findall(text))


def _fake_answer(prompt: AnswerPrompt) -> dict[str, Any]:
    count = len(prompt.passages)
    if not count:
        text = f"{NO_PASSAGE} The fake LLM answers from general knowledge."
        return {"parts": [{"kind": "general", "text": text, "citations": []}]}
    return {
        "parts": [
            {
                "kind": "book",
                "text": "The fake LLM answers from the passages it cites.",
                "citations": [n for n in (1, 2) if n <= count],
            },
            {
                "kind": "synthesis",
                "text": f"The fake LLM sums up {count} passages.",
                "citations": [],
            },
        ]
    }


class FakeLlm:
    """A deterministic LLM that needs no network (ADR 0005).

    Its rewrite appends the last turn's question to the question. It splits a
    search query on " and ", into at most 4 sub-questions. Its answer
    has a book part that cites passages 1 and 2 when the context has them and a
    synthesis part, or the no-passage answer when the context is empty. A
    token is a word, and it costs 0.
    """

    def complete(self, model: str, prompt: Prompt) -> Completion:
        """Return the fake reply to `prompt`, for any model."""
        if isinstance(prompt, RewritePrompt):
            last = prompt.turns[-1].question if prompt.turns else ""
            text = f"{prompt.question} {last}".strip()
        elif isinstance(prompt, DecomposePrompt):
            parts = prompt.query.split(" and ", MAX_SUBQUESTIONS - 1)
            text = json.dumps({"queries": [part.strip() for part in parts]})
        else:
            text = json.dumps(_fake_answer(prompt))
        return self.estimate(model, prompt, text)

    def stream(self, model: str, prompt: Prompt) -> Generator[str | Completion]:
        """Yield the fake reply in chunks of 16 characters, then its completion."""
        completion = self.complete(model, prompt)
        text = completion.text
        for start in range(0, len(text), FAKE_CHUNK):
            yield text[start : start + FAKE_CHUNK]
        yield completion

    def estimate(self, model: str, prompt: Prompt, text: str) -> Completion:  # noqa: ARG002
        """Count the words of the prompt and of `text`, at no cost."""
        sent = " ".join(message["content"] for message in prompt.messages())
        return Completion(text, _words(sent), _words(text), 0.0)


class LiteLlm:
    """Completes through the provider's API with LiteLLM (ADR 0004)."""

    def complete(self, model: str, prompt: Prompt) -> Completion:
        """Return the reply, the tokens the provider counted and LiteLLM's cost."""
        # Imported here, so the fake providers never load LiteLLM.
        import litellm  # noqa: PLC0415

        try:
            response: Any = litellm.completion(
                model=model, messages=prompt.messages(), max_tokens=MAX_OUTPUT_TOKENS
            )
        except Exception as error:
            raise LlmError(str(error)) from error
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=cost(litellm, model, response),
        )

    def stream(self, model: str, prompt: Prompt) -> Generator[str | Completion]:
        """Yield the reply as the provider streams it, then its tokens and cost."""
        import litellm  # noqa: PLC0415

        messages = prompt.messages()
        chunks: list[Any] = []
        try:
            response: Any = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=MAX_OUTPUT_TOKENS,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as error:
            raise LlmError(str(error)) from error
        try:
            for chunk in response:
                chunks.append(chunk)
                text = chunk.choices[0].delta.content if chunk.choices else None
                if isinstance(text, str) and text:
                    yield text
            whole: Any = litellm.stream_chunk_builder(chunks, messages=messages)
        except Exception as error:
            raise LlmError(str(error)) from error
        finally:
            _close_provider_stream(response)
        yield Completion(
            text=whole.choices[0].message.content or "",
            input_tokens=whole.usage.prompt_tokens,
            output_tokens=whole.usage.completion_tokens,
            cost_usd=cost(litellm, model, whole),
        )

    def estimate(self, model: str, prompt: Prompt, text: str) -> Completion:
        """Count the prompt and `text` with the model's tokenizer, and price them."""
        import litellm  # noqa: PLC0415

        input_tokens = litellm.token_counter(model=model, messages=prompt.messages())
        output_tokens = litellm.token_counter(
            model=model, text=text, count_response_tokens=True
        )
        price: float | None = None
        if _has_price(litellm, model):
            try:
                price = sum(
                    litellm.cost_per_token(
                        model=model,
                        prompt_tokens=input_tokens,
                        completion_tokens=output_tokens,
                    )
                )
            except Exception:  # noqa: BLE001 - LiteLLM raises any error for an unknown price
                price = None
        return Completion(text, input_tokens, output_tokens, price)


def _close_provider_stream(response: object) -> None:
    """Close the provider's HTTP stream inside LiteLLM's stream wrapper.

    The wrapper has no `close`. Its `completion_stream` is the provider SDK's
    stream (OpenAI: it has `close`), or LiteLLM's own reader of the HTTP lines
    (Anthropic: the lines are its `streaming_response`).
    """
    stream = getattr(response, "completion_stream", None)
    for target in (stream, getattr(stream, "streaming_response", None)):
        close = getattr(target, "close", None)
        if callable(close):
            close()


def _has_price(litellm: Any, model: str) -> bool:  # noqa: ANN401
    """Return whether LiteLLM's price table has `model`.

    For a model missing from it, LiteLLM can return a cost of 0 instead of
    failing.
    """
    name = litellm.get_llm_provider(model)[0]
    return name in litellm.model_cost or model in litellm.model_cost


def cost(litellm: Any, model: str, response: object) -> float | None:  # noqa: ANN401
    """Return LiteLLM's cost of `response`, or None when it has no price."""
    if not _has_price(litellm, model):
        return None
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception:  # noqa: BLE001 - LiteLLM raises any error for an unknown price
        return None


def make_llm(settings: Settings) -> Llm:
    """Return the fake LLM, or LiteLLM."""
    if settings.ai_providers == "fake":
        return FakeLlm()
    return LiteLlm()
