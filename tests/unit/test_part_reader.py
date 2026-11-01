# Copyright (C) 2026 Theo van Oostrum
"""The reader that finds complete parts in the LLM's streamed JSON answer.

A provider can split its reply at any character, which no route test can place
on purpose; tests/integration/test_chat_stream.py covers the route.
"""

import json

import pytest

from librag.chat import AnswerFormatError, Part, PartReader, parse_answer

FIRST_TEXT = 'A "quoted" claim with {braces} and [brackets].'
FIRST = Part("book", FIRST_TEXT, (1, 2))
PARTS = [
    {
        "kind": "book",
        "text": FIRST_TEXT,
        "citations": [1, 2],
    },
    {"kind": "book", "text": "A back\\slash and a } brace.", "citations": [3]},
    {"kind": "synthesis", "text": "Both agree.", "citations": []},
    {"kind": "general", "text": "Known elsewhere.", "citations": []},
]
REPLY = json.dumps({"parts": PARTS}, indent=1)
FENCED = f"```json\n{REPLY}\n```"
# Where the first part's object ends: after its list of citations.
FIRST_END = REPLY.index("}", REPLY.index("]", REPLY.index('"citations"'))) + 1


def read(chunks: list[str]) -> list[list[Part]]:
    """Feed `chunks` to a reader; return what each feed returned, then `finish`."""
    reader = PartReader()
    return [*(reader.feed(chunk) for chunk in chunks), reader.finish()]


def split(text: str, size: int) -> list[str]:
    """Return `text` in chunks of `size` characters."""
    return [text[i : i + size] for i in range(0, len(text), size)]


@pytest.mark.parametrize("reply", [REPLY, FENCED], ids=["plain", "fenced"])
@pytest.mark.parametrize("size", [1, 2, 3, 7, 64, 100_000])
def test_any_chunking_reads_the_parts_of_parse_answer(reply: str, size: int) -> None:
    """However the reply is split, the reader returns the parts of `parse_answer`."""
    returned = read(split(reply, size))
    assert [part for parts in returned for part in parts] == parse_answer(reply)


def test_a_part_is_returned_once_its_object_is_complete() -> None:
    """Each part comes from the feed that closes its JSON object, not later."""
    reader = PartReader()
    assert reader.feed(REPLY[: FIRST_END - 1]) == []
    assert reader.feed(REPLY[FIRST_END - 1 : FIRST_END]) == [FIRST]


def test_parts_inside_another_key_are_not_parts() -> None:
    """Only the objects in the `parts` list are parts, even in nested objects."""
    reply = json.dumps(
        {
            "notes": [{"kind": "book", "text": "Not a part.", "citations": []}],
            "parts": [
                {"kind": "general", "text": "G.", "citations": [], "x": {"y": [{}]}}
            ],
        }
    )
    returned = [part for parts in read(split(reply, 1)) for part in parts]
    assert returned == [Part("general", "G.")]


def test_reply_with_text_before_the_json_streams_nothing() -> None:
    """A reply that does not start as JSON gives no part early, and then fails."""
    reader = PartReader()
    assert reader.feed(f"Here is the answer: {REPLY}") == []
    with pytest.raises(AnswerFormatError):
        reader.finish()


def test_unfinished_fence_waits() -> None:
    """A reply that may still become a fence gives no part, and no error, yet."""
    reader = PartReader()
    assert reader.feed("``") == []
    assert reader.feed("`js") == []
    assert reader.feed("on\n") == []
    returned = [*reader.feed(REPLY), *reader.feed("\n```")]
    assert [*returned, *reader.finish()] == parse_answer(REPLY)


def test_part_with_an_unknown_kind_fails_as_soon_as_it_is_complete() -> None:
    """A complete part that is not a valid part fails before the reply ends."""
    reader = PartReader()
    with pytest.raises(AnswerFormatError):
        reader.feed('{"parts": [{"kind": "rumour", "text": "R.", "citations": []}')


def test_part_that_is_not_json_fails() -> None:
    """A part object that JSON cannot read fails the answer."""
    reader = PartReader()
    with pytest.raises(AnswerFormatError):
        reader.feed('{"parts": [{"kind": "book", "text": "A.",}')


def test_truncated_reply_fails_at_the_end() -> None:
    """A reply cut off after a part gives that part, then fails at `finish`."""
    reader = PartReader()
    assert reader.feed(REPLY[:FIRST_END]) == [FIRST]
    with pytest.raises(AnswerFormatError):
        reader.finish()


def test_text_after_the_answer_object_is_ignored_while_streaming() -> None:
    """After the top object closes, the reader returns no more parts early."""
    reader = PartReader()
    returned = reader.feed(REPLY + '{"parts": [{"kind": "general", "text": "x"}]}')
    assert len(returned) == len(PARTS)
    with pytest.raises(AnswerFormatError):
        reader.finish()
