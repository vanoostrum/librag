# Copyright (C) 2026 Theo van Oostrum
"""Chat LLMs: LiteLLM, or an in-process fake (ADR 0005)."""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from librag.prompts import NO_PASSAGE, AnswerPrompt, Prompt, RewritePrompt
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

    def stream(self, model: str, prompt: Prompt) -> Iterator[str | Completion]:
        """Yield the reply's text in pieces, then its `Completion`.

        Raise `LlmError` when the provider fails, also halfway.
        """
        ...


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

    Its rewrite appends the last turn's question to the question. Its answer
    has a book part that cites passages 1 and 2 when the context has them and a
    synthesis part, or the no-passage answer when the context is empty. A
    token is a word, and it costs 0.
    """

    def complete(self, model: str, prompt: Prompt) -> Completion:  # noqa: ARG002
        """Return the fake reply to `prompt`, for any model."""
        if isinstance(prompt, RewritePrompt):
            last = prompt.turns[-1].question if prompt.turns else ""
            text = f"{prompt.question} {last}".strip()
        else:
            text = json.dumps(_fake_answer(prompt))
        sent = " ".join(message["content"] for message in prompt.messages())
        return Completion(text, _words(sent), _words(text), 0.0)

    def stream(self, model: str, prompt: Prompt) -> Iterator[str | Completion]:
        """Yield the fake reply in chunks of 16 characters, then its completion."""
        completion = self.complete(model, prompt)
        text = completion.text
        for start in range(0, len(text), FAKE_CHUNK):
            yield text[start : start + FAKE_CHUNK]
        yield completion


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
            cost_usd=_cost(litellm, model, response),
        )

    def stream(self, model: str, prompt: Prompt) -> Iterator[str | Completion]:
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
            for chunk in response:
                chunks.append(chunk)
                text = chunk.choices[0].delta.content if chunk.choices else None
                if isinstance(text, str) and text:
                    yield text
            whole: Any = litellm.stream_chunk_builder(chunks, messages=messages)
        except Exception as error:
            raise LlmError(str(error)) from error
        yield Completion(
            text=whole.choices[0].message.content or "",
            input_tokens=whole.usage.prompt_tokens,
            output_tokens=whole.usage.completion_tokens,
            cost_usd=_cost(litellm, model, whole),
        )


def _cost(litellm: Any, model: str, response: object) -> float | None:  # noqa: ANN401
    """Return LiteLLM's cost of `response`, or None when it has no price.

    For a model missing from its price table, LiteLLM can return 0 instead of
    failing, so the table is checked first.
    """
    name = litellm.get_llm_provider(model)[0]
    if name not in litellm.model_cost and model not in litellm.model_cost:
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
