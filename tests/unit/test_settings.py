# Copyright (C) 2026 Theo van Oostrum
"""An invalid setting stops LibRag from starting. No request can reach that case."""

import pytest
from fastapi.testclient import TestClient

from librag.main import create_app
from librag.settings import SettingsError


def test_invalid_ai_providers_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app does not start when LIBRAG_AI_PROVIDERS is not live or fake."""
    monkeypatch.setenv("LIBRAG_AI_PROVIDERS", "mock")
    with (
        pytest.raises(SettingsError, match="LIBRAG_AI_PROVIDERS") as error,
        TestClient(create_app()),
    ):
        pass
    assert "'mock'" in str(error.value)
