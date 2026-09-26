from __future__ import annotations

from factory.config import Settings
from factory.database import Database


def build_database(settings: Settings):
    url = (settings.database_url or "").strip()
    if url.startswith(("postgres://", "postgresql://")):
        from factory.postgres_database import PostgresDatabase
        return PostgresDatabase(url)
    return Database(settings.db_path)
