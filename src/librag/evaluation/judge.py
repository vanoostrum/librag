# Copyright (C) 2026 Theo van Oostrum
"""The Ragas judge: faithfulness and answer relevancy of one answer.

GPT 6.1 Terra judges both models' answers. Ragas calls OpenAI through its own
client, so the judge reads the tokens from each OpenAI response and prices
them with LiteLLM's price table, as the app does.
"""

import asyncio
import importlib
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

JUDGE_MODEL = "openai/gpt-6.1-terra"
JUDGE_EMBEDDING_MODEL = "openai/text-embedding-3-small"
JUDGE_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class Judgement:
    """The scores of one answer from 0 to 1, and what judging it cost.

    `faithfulness` is None when the answer had no passages to be faithful to.
    `cost_usd` is None when LiteLLM does not know a price.
    """

    faithfulness: float | None
    answer_relevancy: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float


class Judge(Protocol):
    """Scores an answer against its question and the passages it was given."""

    model: str

    def judge(self, question: str, answer: str, contexts: Sequence[str]) -> Judgement:
        """Return the scores of `answer`, and their cost."""
        ...


def _price(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return LiteLLM's price of the tokens, or None when it has no price."""
    # Imported here: LiteLLM loads its price table on import.
    litellm: Any = importlib.import_module("litellm")
    name = model.partition("/")[2]
    entry = litellm.model_cost.get(model) or litellm.model_cost.get(name)
    if not entry:
        return None
    return input_tokens * float(entry.get("input_cost_per_token", 0.0)) + (
        output_tokens * float(entry.get("output_cost_per_token", 0.0))
    )


@dataclass
class _Usage:
    """The tokens of each OpenAI response, by the model the judge asked for."""

    tokens: dict[str, list[int]] = field(default_factory=dict)

    async def read(self, response: Any) -> None:  # noqa: ANN401 - an httpx response
        await response.aread()
        if not response.is_success:
            return
        body = response.json()
        usage = body.get("usage") or {}
        model = JUDGE_EMBEDDING_MODEL if body.get("object") == "list" else JUDGE_MODEL
        counted = self.tokens.setdefault(model, [0, 0])
        counted[0] += int(usage.get("prompt_tokens") or 0)
        counted[1] += int(usage.get("completion_tokens") or 0)

    def cost(self) -> float | None:
        costs = [_price(model, *counted) for model, counted in self.tokens.items()]
        if any(cost is None for cost in costs):
            return None
        return sum(cost for cost in costs if cost is not None)


class RagasJudge:
    """Judges with Ragas, GPT 6.1 Terra and OpenAI's embedder.

    `transport` replaces the network in a smoke test.
    """

    model = JUDGE_MODEL

    def __init__(self, api_key: str | None = None, transport: object = None) -> None:
        """Judge with `api_key`, or `OPENAI_API_KEY` without it."""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.transport = transport
        # Ragas sends usage analytics unless told not to.
        os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

    def judge(self, question: str, answer: str, contexts: Sequence[str]) -> Judgement:
        """Return the faithfulness and answer relevancy of `answer`."""
        start = time.perf_counter()
        usage = _Usage()
        faithfulness, relevancy = asyncio.run(
            self._scores(usage, question, answer, list(contexts))
        )
        input_tokens = sum(counted[0] for counted in usage.tokens.values())
        output_tokens = sum(counted[1] for counted in usage.tokens.values())
        return Judgement(
            faithfulness=faithfulness,
            answer_relevancy=relevancy,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=usage.cost(),
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
        )

    async def _scores(
        self, usage: _Usage, question: str, answer: str, contexts: list[str]
    ) -> tuple[float | None, float | None]:
        # Imported here: Ragas and the OpenAI client are in the `eval` group.
        httpx: Any = importlib.import_module("httpx")
        openai: Any = importlib.import_module("openai")
        llms: Any = importlib.import_module("ragas.llms")
        embeddings: Any = importlib.import_module("ragas.embeddings.base")
        metrics: Any = importlib.import_module("ragas.metrics.collections")
        options: dict[str, Any] = {"event_hooks": {"response": [usage.read]}}
        if self.transport is not None:
            options["transport"] = self.transport
        async with httpx.AsyncClient(timeout=JUDGE_TIMEOUT_SECONDS, **options) as http:
            client = openai.AsyncOpenAI(api_key=self.api_key, http_client=http)
            llm = llms.llm_factory(JUDGE_MODEL.partition("/")[2], client=client)
            embedder = embeddings.embedding_factory(
                "openai", model=JUDGE_EMBEDDING_MODEL.partition("/")[2], client=client
            )
            faithfulness = None
            if contexts:
                result = await metrics.Faithfulness(llm=llm).ascore(
                    user_input=question, response=answer, retrieved_contexts=contexts
                )
                faithfulness = float(result.value)
            result = await metrics.AnswerRelevancy(llm=llm, embeddings=embedder).ascore(
                user_input=question, response=answer
            )
            return faithfulness, float(result.value)
