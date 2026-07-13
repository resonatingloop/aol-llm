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
        "buddy_memories",
        "buddies",
        "conversations",
        "memory_distill_runs",
        "messages",
        "prompt_versions",
        "prompts",
        "providers",
    }
    assert connection.execute("SELECT COUNT(*) FROM prompts").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM buddies").fetchone()[0] == 6
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
    assert {
        row[0]
        for row in connection.execute(
            "SELECT model FROM buddies WHERE provider_id = 'openai'"
        )
    } == {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
    memory_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('buddy_memories')")
    }
    message_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('messages')")
    }
    assert memory_columns >= {
        "buddy_id",
        "memory_text",
        "enabled",
        "suppress_injection",
        "watermark_created_at",
        "watermark_message_id",
        "updated_at",
    }
    assert message_columns >= {
        "cache_creation_5m_input_tokens",
        "cache_creation_1h_input_tokens",
        "cache_read_input_tokens",
    }
    distill_run_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('memory_distill_runs')")
    }
    assert distill_run_columns >= {
        "id",
        "buddy_id",
        "provider_id",
        "model",
        "mode",
        "status",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "watermark_created_at",
        "watermark_message_id",
        "failure_reason",
        "created_at",
    }


def test_gpt_5_6_migration_does_not_duplicate_archived_buddies() -> None:
    connection = sqlite3.connect(":memory:")
    apply_all_migrations(connection)
    connection.execute("UPDATE buddies SET archived = 1 WHERE model = 'gpt-5.6-sol'")

    migration = pathlib.Path(
        "src/aol_llm/storage/migrations/008_openai_gpt_5_6.sql"
    ).read_text()
    connection.executescript(migration)

    assert (
        connection.execute(
            "SELECT COUNT(*) FROM buddies WHERE model = 'gpt-5.6-sol'"
        ).fetchone()[0]
        == 1
    )
    assert (
        connection.execute(
            "SELECT archived FROM buddies WHERE model = 'gpt-5.6-sol'"
        ).fetchone()[0]
        == 1
    )


def test_buddy_memory_cascades_with_buddy_delete() -> None:
    connection = sqlite3.connect(":memory:")
    apply_all_migrations(connection)
    buddy_id = connection.execute(
        "SELECT id FROM buddies ORDER BY created_at LIMIT 1"
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO buddy_memories (buddy_id, memory_text, updated_at)
        VALUES (?, 'remember this', 'now')
        """,
        (buddy_id,),
    )

    connection.execute("DELETE FROM buddies WHERE id = ?", (buddy_id,))

    assert connection.execute("SELECT COUNT(*) FROM buddy_memories").fetchone()[0] == 0


def test_memory_distill_runs_cascade_with_buddy_delete() -> None:
    connection = sqlite3.connect(":memory:")
    apply_all_migrations(connection)
    buddy_id = connection.execute(
        "SELECT id FROM buddies ORDER BY created_at LIMIT 1"
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO memory_distill_runs
            (id, buddy_id, provider_id, model, mode, status, created_at)
        VALUES
            ('run-id', ?, 'anthropic', 'claude-opus-4-8', 'incremental',
             'noop', 'now')
        """,
        (buddy_id,),
    )

    connection.execute("DELETE FROM buddies WHERE id = ?", (buddy_id,))

    assert (
        connection.execute("SELECT COUNT(*) FROM memory_distill_runs").fetchone()[0]
        == 0
    )


def test_buddy_memory_watermark_requires_complete_pair() -> None:
    connection = sqlite3.connect(":memory:")
    apply_all_migrations(connection)
    buddy_id = connection.execute(
        "SELECT id FROM buddies ORDER BY created_at LIMIT 1"
    ).fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO buddy_memories
                (buddy_id, memory_text, watermark_created_at, updated_at)
            VALUES (?, '', '2026-06-13T00:00:00+00:00', 'now')
            """,
            (buddy_id,),
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
