from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import pathlib
import sqlite3

import pytest

from aol_llm.core.errors import AuthError, ProviderError
from aol_llm.core.types import (
    Conversation,
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)


def test_core_value_types_are_frozen() -> None:
    created_at = datetime.now(UTC)
    message = Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=created_at,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(message, "content", "changed")


def test_provider_config_and_stream_chunk_shapes() -> None:
    config = ProviderConfig(
        id="anthropic",
        kind="anthropic",
        display_name="Anthropic",
        base_url=None,
        keyring_service="aol-llm.anthropic",
        default_model="claude-sonnet-4-6",
        available_models=["claude-sonnet-4-6"],
    )
    usage = TokenUsage(input_tokens=10, output_tokens=20, model=config.default_model)
    chunk = StreamChunk(text="", done=True, usage=usage)

    assert config.kind == "anthropic"
    assert chunk.done is True
    assert chunk.usage == usage


def test_conversation_stores_system_prompt_outside_messages() -> None:
    now = datetime.now(UTC)
    conversation = Conversation(
        id="conversation-id",
        title="test",
        system_prompt="You are concise.",
        provider_id="anthropic",
        model="claude-sonnet-4-6",
        created_at=now,
        updated_at=now,
    )

    assert conversation.system_prompt == "You are concise."


def test_provider_errors_share_base_class() -> None:
    assert issubclass(AuthError, ProviderError)


def test_initial_migration_applies_to_sqlite() -> None:
    migration = pathlib.Path("src/aol_llm/storage/migrations/001_init.sql").read_text()
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(migration)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }

    assert tables == {"app_settings", "conversations", "messages", "providers"}
