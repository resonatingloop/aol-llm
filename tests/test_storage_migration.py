import pathlib
import sqlite3

import pytest


def apply_initial_migration(connection: sqlite3.Connection) -> None:
    migration = pathlib.Path("src/aol_llm/storage/migrations/001_init.sql").read_text()
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(migration)


def apply_all_migrations(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for migration in sorted(
        pathlib.Path("src/aol_llm/storage/migrations").glob("*.sql")
    ):
        connection.executescript(migration.read_text())


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


def test_all_migrations_add_buddy_prompt_tables_and_seed_defaults() -> None:
    connection = sqlite3.connect(":memory:")
    apply_all_migrations(connection)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }

    assert tables == {
        "app_settings",
        "buddies",
        "conversations",
        "messages",
        "prompt_versions",
        "prompts",
        "providers",
    }
    assert connection.execute("SELECT COUNT(*) FROM prompts").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM buddies").fetchone()[0] == 3
    assert (
        connection.execute(
            """
            SELECT COUNT(*)
            FROM buddies
            WHERE provider_id = 'anthropic'
              AND model = 'claude-opus-4-8'
            """
        ).fetchone()[0]
        == 1
    )
    assert (
        connection.execute(
            """
            SELECT COUNT(*)
            FROM buddies
            WHERE provider_id = 'anthropic'
              AND model = 'claude-fable-5'
            """
        ).fetchone()[0]
        == 1
    )


def test_prompt_migration_links_existing_conversations_and_assistant_messages() -> None:
    connection = sqlite3.connect(":memory:")
    apply_initial_migration(connection)
    connection.execute(
        """
        INSERT INTO conversations
            (id, title, system_prompt, provider_id, model, created_at, updated_at)
        VALUES
            ('conversation-a', 'A', 'Be concise.', 'anthropic', 'model', 'now', 'now'),
            ('conversation-b', 'B', 'Be concise.', 'anthropic', 'model', 'now', 'now'),
            ('conversation-c', 'C', NULL, 'openai', 'gpt-test', 'now', 'now')
        """
    )
    connection.execute(
        """
        INSERT INTO messages
            (id, conversation_id, role, content, created_at)
        VALUES
            ('user-message', 'conversation-a', 'user', 'hello', 'now'),
            ('assistant-message', 'conversation-a', 'assistant', 'hi', 'now')
        """
    )

    second = pathlib.Path("src/aol_llm/storage/migrations/002_buddies_prompts.sql")
    connection.executescript(second.read_text())

    migrated_prompt_count = connection.execute(
        "SELECT COUNT(*) FROM prompts WHERE name LIKE 'Migrated Away Message%'"
    ).fetchone()[0]
    linked_versions = {
        row[0]
        for row in connection.execute(
            """
            SELECT prompt_version_id
            FROM conversations
            WHERE id IN ('conversation-a', 'conversation-b')
            """
        )
    }
    assistant_prompt_version = connection.execute(
        "SELECT prompt_version_id FROM messages WHERE id = 'assistant-message'"
    ).fetchone()[0]
    user_prompt_version = connection.execute(
        "SELECT prompt_version_id FROM messages WHERE id = 'user-message'"
    ).fetchone()[0]

    assert migrated_prompt_count == 1
    assert len(linked_versions) == 1
    assert assistant_prompt_version in linked_versions
    assert user_prompt_version is None


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
