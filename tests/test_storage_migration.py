import pathlib
import sqlite3

import pytest


def apply_initial_migration(connection: sqlite3.Connection) -> None:
    migration = pathlib.Path("src/aol_llm/storage/migrations/001_init.sql").read_text()
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(migration)


def test_initial_migration_applies_to_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    apply_initial_migration(connection)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }

    assert tables == {"app_settings", "conversations", "messages", "providers"}


def test_message_role_constraint_rejects_system_messages() -> None:
    connection = sqlite3.connect(":memory:")
    apply_initial_migration(connection)
    connection.execute(
        """
        INSERT INTO conversations
            (id, title, provider_id, model, created_at, updated_at)
        VALUES
            ('conversation-id', 'test', 'anthropic', 'model', 'now', 'now')
        """
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, created_at)
            VALUES
                ('message-id', 'conversation-id', 'system', 'nope', 'now')
            """
        )


def test_conversation_delete_cascades_messages() -> None:
    connection = sqlite3.connect(":memory:")
    apply_initial_migration(connection)
    connection.execute(
        """
        INSERT INTO conversations
            (id, title, provider_id, model, created_at, updated_at)
        VALUES
            ('conversation-id', 'test', 'anthropic', 'model', 'now', 'now')
        """
    )
    connection.execute(
        """
        INSERT INTO messages
            (id, conversation_id, role, content, created_at)
        VALUES
            ('message-id', 'conversation-id', 'user', 'hello', 'now')
        """
    )

    connection.execute("DELETE FROM conversations WHERE id = 'conversation-id'")
    message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    assert message_count == 0
