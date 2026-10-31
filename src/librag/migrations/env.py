# Copyright (C) 2026 Theo van Oostrum
"""Alembic environment: migrate the database from the LibRag settings."""

from alembic import context
from sqlalchemy import create_engine

from librag.db import metadata
from librag.settings import Settings

config = context.config
url = config.get_main_option("sqlalchemy.url") or Settings.from_env().database_url

engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
