from pathlib import Path
import sqlite3

import pytest

from aol_llm.core.types import ProviderConfig
from aol_llm.storage import db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "aol-llm.db"
    db.init_db(path)
    return path


def test_init_db_applies_migrations_idempotently(db_path: Path) -> None:
    db.init_db(db_path)

    with db.get_connection(db_path) as connection:
        applied = [
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        ]

    assert applied == ["001_init"]


def test_conversation_crud_and_archive_filtering(db_path: Path) -> None:
    conversation = db.create_conversation(
        title="First chat",
        provider_id="anthropic",
        model="claude-sonnet-test",
        system_prompt="Be concise.",
        path=db_path,
    )

    fetched = db.get_conversation(conversation.id, db_path)
    assert fetched == conversation
    assert db.list_conversations(path=db_path) == [conversation]

    updated = db.update_conversation(
        conversation.id,
        path=db_path,
        title="Renamed",
        archived=True,
    )

    assert updated.title == "Renamed"
    assert updated.archived is True
    assert updated.updated_at >= conversation.updated_at
    assert db.list_conversations(path=db_path) == []
    assert db.list_conversations(include_archived=True, path=db_path) == [updated]


def test_messages_preserve_usage_fields_and_order(db_path: Path) -> None:
    conversation = db.create_conversation(
        title="Chat",
        provider_id="anthropic",
        model="claude-sonnet-test",
        path=db_path,
    )
    user_message = db.add_message(
        conversation_id=conversation.id,
        role="user",
        content="hello",
        path=db_path,
    )
    assistant_message = db.add_message(
        conversation_id=conversation.id,
        role="assistant",
        content="hi",
        path=db_path,
        model="claude-sonnet-test",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    )

    messages = db.list_messages(conversation.id, db_path)

    assert messages == [user_message, assistant_message]
    assert messages[1].model == "claude-sonnet-test"
    assert messages[1].input_tokens == 10
    assert messages[1].output_tokens == 20
    assert messages[1].cost_usd == 0.001


def test_delete_conversation_cascades_messages(db_path: Path) -> None:
    conversation = db.create_conversation("Chat", "anthropic", "model", path=db_path)
    db.add_message(conversation.id, "user", "hello", path=db_path)

    db.delete_conversation(conversation.id, db_path)

    assert db.list_messages(conversation.id, db_path) == []


def test_add_message_enforces_conversation_foreign_key(db_path: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.add_message("missing", "user", "hello", path=db_path)


def test_provider_config_upsert_and_list(db_path: Path) -> None:
    original = ProviderConfig(
        id="openai",
        kind="openai_compatible",
        display_name="OpenAI",
        base_url="https://api.openai.test/v1",
        keyring_service="aol-llm.openai",
        default_model="gpt-test",
        available_models=["gpt-test"],
    )
    updated = ProviderConfig(
        id="openai",
        kind="openai_compatible",
        display_name="OpenAI",
        base_url="https://api.openai.test/v1",
        keyring_service="aol-llm.openai",
        default_model="gpt-new",
        available_models=["gpt-new", "gpt-test"],
    )

    db.save_provider(original, db_path)
    db.save_provider(updated, db_path)

    assert db.list_providers(db_path) == [updated]


def test_app_settings_upsert(db_path: Path) -> None:
    db.set_app_setting("theme", "default", db_path)
    db.set_app_setting("theme", "dark", db_path)

    assert db.get_app_setting("theme", db_path) == "dark"
    assert db.get_app_setting("missing", db_path) is None
