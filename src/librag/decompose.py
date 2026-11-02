# Copyright (C) 2026 Theo van Oostrum
"""Decomposition: split a complex search query into sub-questions (LIBRAG_DECOMPOSE).

The LLM decides whether to split. A query it does not split stays the one
search query. A decomposition never fails a request: a reply that is not the
JSON the prompt asks for, and a provider error, keep the one search query.
"""

import json
from collections.abc import Callable

from librag.llm import Completion, LlmError, strip_fence
from librag.prompts import MAX_SUBQUESTIONS, DecomposePrompt


def parse_queries(text: str, query: str) -> list[str]:
    """Return the sub-questions in the LLM's reply, or `[query]`.

    Blank, repeated and non-text entries are left out, and only the first 4
    count. A reply with fewer than 2 sub-questions keeps the search query, so a
    query that is not split takes the normal path.
    """
    try:
        data = json.loads(strip_fence(text))
    except json.JSONDecodeError:
        return [query]
    found = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(found, list):
        return [query]
    texts = [str(item).strip() for item in found if isinstance(item, str)]
    queries = list(dict.fromkeys(text for text in texts if text))[:MAX_SUBQUESTIONS]
    return queries if len(queries) > 1 else [query]


def decompose(
    complete: Callable[[DecomposePrompt], Completion], query: str
) -> list[str]:
    """Return the sub-questions of `query`, asked for with `complete`, or `[query]`."""
    try:
        completion = complete(DecomposePrompt(query))
    except LlmError:
        return [query]
    return parse_queries(completion.text, query)
