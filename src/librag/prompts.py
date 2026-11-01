# Copyright (C) 2026 Theo van Oostrum
"""The prompts that chat sends to the LLM: rewrite a follow-up, and answer."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NO_PASSAGE = "Your books hold no passage on this."

ANSWER_INSTRUCTIONS = f"""\
You answer questions about the user's books, from the numbered passages of those \
books that come with the question.

Reply with only a JSON object, with no other text, in this shape:
{{"parts": [{{"kind": "book", "text": "...", "citations": [1, 2]}}]}}

The kinds of part:
- "book": one claim that the passages support. Its citations are the numbers of \
the passages that support it. Write one book part per claim.
- "synthesis": your conclusion that connects the book claims. At most one.
- "general": what you add from general knowledge, not from the passages. At most \
one, with no citations.

Leave out a kind you do not need. Cite only the numbers of the passages given. \
When no passage helps to answer the question, answer from general knowledge in \
one general part that starts with "{NO_PASSAGE}"
"""

REWRITE_INSTRUCTIONS = """\
Rewrite the user's last question as a standalone search query for passages in \
their books. Use the conversation to fill in what the question refers to. Reply \
with only the query.
"""

Message = dict[str, str]


@dataclass(frozen=True)
class Turn:
    """An earlier question in the conversation, and the answer it got."""

    question: str
    answer: str


def _history(turns: Sequence[Turn]) -> list[Message]:
    messages: list[Message] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    return messages


def _passage(n: int, passage: Mapping[str, Any]) -> str:
    source = ", ".join(
        part
        for part in (
            passage["title"],
            passage["author"] and f"by {passage['author']}",
            passage["chapter"],
            passage["section"],
        )
        if part
    )
    return f"[{n}] {source}\n{passage['text']}"


@dataclass(frozen=True)
class RewritePrompt:
    """Asks for a standalone search query for a follow-up question."""

    question: str
    turns: Sequence[Turn]

    def messages(self) -> list[Message]:
        """Return the chat messages for the LLM."""
        return [
            {"role": "system", "content": REWRITE_INSTRUCTIONS},
            *_history(self.turns),
            {"role": "user", "content": self.question},
        ]


@dataclass(frozen=True)
class AnswerPrompt:
    """Asks for an answer in parts, citing the context passages by number.

    `passages` are search results; the prompt numbers them from 1.
    """

    question: str
    passages: Sequence[Mapping[str, Any]]
    turns: Sequence[Turn] = ()

    def messages(self) -> list[Message]:
        """Return the chat messages for the LLM."""
        numbered = "\n\n".join(
            _passage(n, passage) for n, passage in enumerate(self.passages, start=1)
        )
        context = f"Passages:\n\n{numbered}" if numbered else "Passages: none."
        return [
            {"role": "system", "content": ANSWER_INSTRUCTIONS},
            *_history(self.turns),
            {"role": "user", "content": f"{context}\n\nQuestion: {self.question}"},
        ]


Prompt = RewritePrompt | AnswerPrompt
