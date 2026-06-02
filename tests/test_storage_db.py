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

    assert applied == [
        "001_init",
        "002_buddies_prompts",
        "003_anthropic_opus_4_8",
        "004_conversation_assistant_name",
    ]


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


def test_conversation_reply_name_override_can_be_set_and_cleared(
    db_path: Path,
) -> None:
    conversation = db.create_conversation(
        title="First chat",
        provider_id="anthropic",
        model="claude-sonnet-test",
        path=db_path,
    )

    updated = db.update_conversation(
        conversation.id,
        path=db_path,
        assistant_name="Threshold",
    )
    cleared = db.update_conversation(
        conversation.id,
        path=db_path,
        assistant_name=None,
    )

    assert conversation.assistant_name is None
    assert updated.assistant_name == "Threshold"
    assert cleared.assistant_name is None


def test_list_conversations_for_buddy_filters_history(db_path: Path) -> None:
    first_buddy = db.ensure_buddy("anthropic", "claude-a", db_path)
    second_buddy = db.ensure_buddy("anthropic", "claude-b", db_path)
    first_chat = db.create_conversation(
        "First",
        first_buddy.provider_id,
        first_buddy.model,
        buddy_id=first_buddy.id,
        prompt_version_id=first_buddy.prompt_version_id,
        path=db_path,
    )
    archived_chat = db.create_conversation(
        "Archived",
        first_buddy.provider_id,
        first_buddy.model,
        buddy_id=first_buddy.id,
        prompt_version_id=first_buddy.prompt_version_id,
        path=db_path,
    )
    second_chat = db.create_conversation(
        "Second",
        second_buddy.provider_id,
        second_buddy.model,
        buddy_id=second_buddy.id,
        prompt_version_id=second_buddy.prompt_version_id,
        path=db_path,
    )

    archived_chat = db.update_conversation(
        archived_chat.id,
        path=db_path,
        archived=True,
    )

    assert db.list_conversations_for_buddy(first_buddy.id, path=db_path) == [first_chat]
    assert db.list_conversations_for_buddy(
        first_buddy.id,
        include_archived=True,
        path=db_path,
    ) == [archived_chat, first_chat]
    assert db.list_conversations_for_buddy(second_buddy.id, path=db_path) == [
        second_chat
    ]


def test_messages_preserve_usage_fields_and_order(db_path: Path) -> None:
    conversation = db.create_conversation(
        title="Chat",
        provider_id="anthropic",
        model="claude-sonnet-test",
        path=db_path,
    )
    prompt = db.create_prompt("Away", "gloss", "Be brief.", path=db_path)
    version = db.create_prompt_version(prompt, path=db_path)
    db.update_prompt_current_version(prompt.id, version.id, db_path)
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
        prompt_version_id=version.id,
    )

    messages = db.list_messages(conversation.id, db_path)

    assert messages == [user_message, assistant_message]
    assert messages[1].model == "claude-sonnet-test"
    assert messages[1].input_tokens == 10
    assert messages[1].output_tokens == 20
    assert messages[1].cost_usd == 0.001
    assert messages[1].prompt_version_id == version.id


def test_delete_message_removes_only_that_message(db_path: Path) -> None:
    conversation = db.create_conversation("Chat", "anthropic", "model", path=db_path)
    first = db.add_message(conversation.id, "user", "hello", path=db_path)
    second = db.add_message(conversation.id, "assistant", "hi", path=db_path)

    db.delete_message(second.id, db_path)

    assert db.list_messages(conversation.id, db_path) == [first]


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


def test_seeded_default_prompt_and_buddy_are_available(db_path: Path) -> None:
    version = db.default_prompt_version(db_path)
    prompts = db.list_prompts(path=db_path)
    buddies = db.list_buddies(path=db_path)

    assert version.name == "Available"
    assert prompts[0].current_version_id == version.id
    assert buddies[0].prompt_version_id == version.id


def test_prompt_version_snapshots_and_rollback_pointer(db_path: Path) -> None:
    prompt = db.create_prompt(
        "Away",
        "short gloss",
        "Be exact.",
        path=db_path,
        status="canonical",
        doorwords="warp",
    )
    first = db.create_prompt_version(prompt, path=db_path, note="initial")
    updated = db.update_prompt_current_version(prompt.id, first.id, db_path)

    assert first.core == "Be exact."
    assert first.doorwords == "warp"
    assert first.note == "initial"
    assert updated.current_version_id == first.id


def test_ensure_buddy_reuses_provider_model_pair(db_path: Path) -> None:
    first = db.ensure_buddy("anthropic", "claude-test", db_path)
    second = db.ensure_buddy("anthropic", "claude-test", db_path)

    assert first == second
    assert first.prompt_version_id == db.default_prompt_version(db_path).id


def test_update_buddy_renames_display_fields(db_path: Path) -> None:
    buddy = db.ensure_buddy("anthropic", "claude-test", db_path)

    updated = db.update_buddy(
        buddy.id,
        db_path,
        name="Threshold",
        screen_name="Threshold",
    )

    assert updated.name == "Threshold"
    assert updated.screen_name == "Threshold"
    assert updated.provider_id == buddy.provider_id
    assert updated.model == buddy.model
