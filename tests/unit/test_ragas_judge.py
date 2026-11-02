# Copyright (C) 2026 Theo van Oostrum
"""The Ragas judge, wired to Ragas with a stand-in for the OpenAI API.

A real judgement costs money, so no request can test the wiring. The
stand-in answers each Ragas prompt with a fixed JSON object, which shows that
the judge calls Ragas the way this Ragas version expects, and counts the
tokens and cost of every OpenAI response.
"""

import json

import httpx
import pytest

from librag.evaluation.judge import RagasJudge

CHAT_TOKENS = (100, 20)
EMBEDDING_TOKENS = 7


def _reply(prompt: str) -> dict[str, object]:
    """Return the JSON object that a Ragas prompt asks for."""
    if "verdict" in prompt:
        return {"statements": [{"statement": "s", "reason": "r", "verdict": 1}]}
    if "noncommittal" in prompt:
        return {"question": "Who polished the brass lamp?", "noncommittal": 0}
    return {"statements": ["The keeper polished the lamp."]}


def _openai(requests: list[str]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(request.url.path)
        if request.url.path.endswith("/embeddings"):
            texts = (
                body["input"] if isinstance(body["input"], list) else [body["input"]]
            )
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [1.0, 0.5]}
                        for i in range(len(texts))
                    ],
                    "model": "text-embedding-3-small",
                    "usage": {
                        "prompt_tokens": EMBEDDING_TOKENS,
                        "total_tokens": EMBEDDING_TOKENS,
                    },
                },
            )
        content = json.dumps(_reply(json.dumps(body["messages"])))
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-6.1-terra",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": CHAT_TOKENS[0],
                    "completion_tokens": CHAT_TOKENS[1],
                    "total_tokens": sum(CHAT_TOKENS),
                },
            },
        )

    return httpx.MockTransport(handle)


def test_judge_scores_and_counts_every_openai_call() -> None:
    """Faithfulness and relevancy come from Ragas; tokens from each response."""
    requests: list[str] = []
    judge = RagasJudge(api_key="sk-test", transport=_openai(requests))
    judgement = judge.judge(
        "Who polished the brass lamp?",
        "The lighthouse keeper polished the lamp.",
        ["The lighthouse keeper polished the brass lamp every evening."],
    )
    assert judgement.faithfulness == 1.0
    # Every generated question embeds like the question, so it is fully relevant.
    assert judgement.answer_relevancy == pytest.approx(1.0)
    chats = requests.count("/v1/chat/completions")
    embeddings = requests.count("/v1/embeddings")
    assert chats >= 2  # noqa: PLR2004 - statements, then verdicts, then questions
    assert embeddings >= 1
    assert judgement.input_tokens == chats * CHAT_TOKENS[0] + (
        embeddings * EMBEDDING_TOKENS
    )
    assert judgement.output_tokens == chats * CHAT_TOKENS[1]
    assert judgement.cost_usd is None or judgement.cost_usd > 0
    assert judgement.latency_ms > 0


def test_answer_without_passages_has_no_faithfulness() -> None:
    """Without passages there is nothing to be faithful to; relevancy still counts."""
    requests: list[str] = []
    judge = RagasJudge(api_key="sk-test", transport=_openai(requests))
    judgement = judge.judge("Who won the chess championship?", "Not in the books.", [])
    assert judgement.faithfulness is None
    assert judgement.answer_relevancy is not None
