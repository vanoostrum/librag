# Copyright (C) 2026 Theo van Oostrum
"""Settings that the api and the worker read from `LIBRAG_*` environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

AiProviders = Literal["live", "fake"]
AI_PROVIDERS_VALUES: tuple[AiProviders, ...] = ("live", "fake")


class SettingsError(ValueError):
    """A `LIBRAG_*` environment variable has a value that LibRag cannot use."""


@dataclass(frozen=True)
class Settings:
    """Where LibRag finds Qdrant, its metadata database and its file store."""

    qdrant_url: str = "http://localhost:6333"
    database_url: str = "sqlite:///data/librag.db"
    file_store_dir: str = "data/files"
    ai_providers: AiProviders = "live"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Read the settings from the environment, with a default for each one."""
        env = os.environ if environ is None else environ
        defaults = cls()
        ai_providers = env.get("LIBRAG_AI_PROVIDERS", defaults.ai_providers)
        if ai_providers not in AI_PROVIDERS_VALUES:
            msg = f"LIBRAG_AI_PROVIDERS must be 'live' or 'fake', not {ai_providers!r}"
            raise SettingsError(msg)
        return cls(
            qdrant_url=env.get("LIBRAG_QDRANT_URL", defaults.qdrant_url),
            database_url=env.get("LIBRAG_DATABASE_URL", defaults.database_url),
            file_store_dir=env.get("LIBRAG_FILE_STORE_DIR", defaults.file_store_dir),
            ai_providers=ai_providers,
        )
