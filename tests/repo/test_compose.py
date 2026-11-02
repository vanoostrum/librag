# Copyright (C) 2026 Theo van Oostrum
"""The test stack uses the fake AI providers, so required CI never needs API keys."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
APP_SERVICES = ("migrate", "api", "worker")


def services(name: str) -> dict[str, dict[str, Any]]:
    """Return the services of a Compose file in the repo root."""
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))["services"]


def env_file_values(paths: list[str]) -> dict[str, str]:
    """Return the variables that a list of Compose env files sets."""
    values: dict[str, str] = {}
    for path in paths:
        for raw in (ROOT / path).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                values[key] = value
    return values


@pytest.mark.parametrize("service", APP_SERVICES)
def test_test_overlay_selects_fake_ai_providers(service: str) -> None:
    """compose.test.yaml sets LIBRAG_AI_PROVIDERS=fake, and compose.yaml keeps it."""
    overlay = services("compose.test.yaml")[service]
    assert env_file_values(overlay["env_file"])["LIBRAG_AI_PROVIDERS"] == "fake"
    # `environment` wins over `env_file` in Compose, so it must not set the switch.
    for compose_file in ("compose.yaml", "compose.test.yaml"):
        environment = services(compose_file)[service].get("environment", {})
        assert "LIBRAG_AI_PROVIDERS" not in environment, compose_file


@pytest.mark.parametrize("service", APP_SERVICES)
@pytest.mark.parametrize("key", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
def test_compose_passes_the_provider_keys_through(service: str, key: str) -> None:
    """compose.yaml passes each provider key from the shell, unset in the file."""
    environment = services("compose.yaml")[service]["environment"]
    assert key in environment
    assert environment[key] is None


def test_live_reports_are_not_committed() -> None:
    """The live run's reports in e2e-reports/ are ignored by git."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "e2e-reports/" in ignored


# compose.yaml sets these for the containers, and the test overlay sets the providers.
SET_IN_COMPOSE = {
    "LIBRAG_QDRANT_URL",
    "LIBRAG_DATABASE_URL",
    "LIBRAG_FILE_STORE_DIR",
    "LIBRAG_AI_PROVIDERS",
}
# Compose reads these itself, to pick the published ports.
COMPOSE_PORTS = {"LIBRAG_PORT", "LIBRAG_QDRANT_PORT"}


def setting_names() -> set[str]:
    """Return every `LIBRAG_*` variable that the app's settings read."""
    source = (ROOT / "src/librag/settings.py").read_text(encoding="utf-8")
    return set(re.findall(r'"(LIBRAG_[A-Z0-9_]+)"', source))


def env_example_names() -> set[str]:
    """Return the variables that .env.example sets or shows commented out."""
    names: set[str] = set()
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        found = re.match(r"#?\s*([A-Z][A-Z0-9_]*)=", raw.strip())
        if found:
            names.add(str(found.group(1)))
    return names


@pytest.mark.parametrize("service", APP_SERVICES)
def test_compose_passes_every_setting_through(service: str) -> None:
    """Each setting in the shell or .env reaches the containers, unset in the file."""
    environment = services("compose.yaml")[service]["environment"]
    for name in sorted(setting_names() - SET_IN_COMPOSE):
        assert name in environment, name
        assert environment[name] is None, name


def test_env_example_names_only_what_compose_uses() -> None:
    """Every variable in .env.example reaches the stack, so none is set in vain."""
    environment = services("compose.yaml")["api"]["environment"]
    names = env_example_names()
    assert {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"} <= names
    for name in sorted(names):
        assert name in environment or name in COMPOSE_PORTS, name


def test_env_example_holds_no_key() -> None:
    """.env.example is committed, so its keys are empty."""
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, _, value = raw.strip().partition("=")
        if key.endswith("_API_KEY"):
            assert value == "", key
