# Copyright (C) 2026 Theo van Oostrum
"""The parsing of the LLM's reply to the decompose prompt.

The reply has many malformed shapes, which are slow to reach one by one
through POST /api/chat; tests/integration/test_decompose.py covers the routes.
"""

import json

import pytest

from librag.decompose import parse_queries

QUERY = "lamps and ships"


def _reply(queries: object) -> str:
    return json.dumps({"queries": queries})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(_reply(["lamps", "ships"]), ["lamps", "ships"], id="two queries"),
        pytest.param(
            f"```json\n{_reply(['lamps', 'ships'])}\n```",
            ["lamps", "ships"],
            id="in a code fence",
        ),
        pytest.param(
            _reply([" lamps ", "", "  ", 7, None, "ships"]),
            ["lamps", "ships"],
            id="blank and non-text queries are left out",
        ),
        pytest.param(
            _reply(["a", "b", "c", "d", "e", "f"]),
            ["a", "b", "c", "d"],
            id="more than 4 keeps the first 4",
        ),
        pytest.param(
            _reply(["lamps", "ships", "lamps"]),
            ["lamps", "ships"],
            id="a repeated query is kept once",
        ),
        pytest.param(_reply(["lamps"]), [QUERY], id="one query keeps the search query"),
        pytest.param(_reply([]), [QUERY], id="empty list"),
        pytest.param(_reply("lamps"), [QUERY], id="queries is not a list"),
        pytest.param(json.dumps({"parts": []}), [QUERY], id="no queries key"),
        pytest.param(json.dumps(["lamps", "ships"]), [QUERY], id="not an object"),
        pytest.param("lamps, ships", [QUERY], id="not JSON"),
        pytest.param("", [QUERY], id="empty reply"),
    ],
)
def test_reply_gives_the_queries(text: str, expected: list[str]) -> None:
    """A valid reply gives its queries; anything else falls back to the query."""
    assert parse_queries(text, QUERY) == expected
