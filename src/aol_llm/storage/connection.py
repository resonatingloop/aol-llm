"""SQLite connection and migration helpers."""

from collections.abc import Iterable
from pathlib import Path
import sqlite3
from typing import cast

from aol_llm.config import database_path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(path: Path | None = None) -> None:
    with get_connection(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY
            )
            """
        )
        applied = {
            cast(str, row["version"])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for migration in _migration_files():
            version = migration.stem
            if version in applied:
                continue
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )


def _migration_files() -> Iterable[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))
