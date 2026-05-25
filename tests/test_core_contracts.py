from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from aol_llm.core.errors import AuthError, ProviderError
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd
from aol_llm.core.requests import normalize_chat_request
from aol_llm.core.types import (
    Conversation,
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)


def test_core_value_types_are_frozen() -> None:
    message = Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(FrozenInstanceError):
        setattr(message, "content", "changed")


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


def test_provider_errors_share_base_class() -> None:
    assert issubclass(AuthError, ProviderError)


def test_normalize_chat_request_keeps_system_separate() -> None:
    message = Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=datetime.now(UTC),
    )
    normalized = normalize_chat_request(
        messages=[message],
        system="You are concise.",
        model="claude-sonnet-4-6",
    )

    assert normalized.messages == (message,)
    assert normalized.system == "You are concise."
    assert normalized.messages[0].role == "user"


def test_estimate_cost_usd_uses_per_million_token_rates() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000, model="model-a")
    rate_card = {"model-a": ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0)}

    assert estimate_cost_usd(usage, rate_card) == 10.5


def test_estimate_cost_usd_returns_none_for_unknown_models() -> None:
    usage = TokenUsage(input_tokens=1, output_tokens=1, model="unknown")

    assert estimate_cost_usd(usage, {}) is None
