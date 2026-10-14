# Copyright (C) 2026 Theo van Oostrum
"""Unit tests for the health route function."""

from librag.main import health


def test_health_returns_ok() -> None:
    """The health route returns the ok status payload."""
    assert health() == {"status": "ok"}
