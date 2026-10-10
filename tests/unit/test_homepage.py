# Copyright (C) 2026 Theo van Oostrum
"""Unit tests for the homepage route function."""

from librag.main import homepage


def test_homepage_contains_title() -> None:
    """The homepage HTML contains the LibRag title and heading."""
    page = homepage()
    assert "<title>LibRag</title>" in page
    assert "<h1>LibRag</h1>" in page
