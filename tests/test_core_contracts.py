from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from aol_llm.core.errors import AuthError, ProviderError
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd, load_rate_card
from aol_llm.core.requests import normalize_chat_request
from aol_llm.core.types import (
    Buddy,
    BuddyMemory,
    Conversation,
    Message,
    Prompt,
    PromptVersion,
    ProviderConfig,
    ProviderResponseMetadata,
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


def test_buddy_and_prompt_types_capture_current_state_and_versions() -> None:
    now = datetime.now(UTC)
    prompt = Prompt(
        id="prompt-id",
        name="Away",
        gloss="gone testing",
        core="Be precise.",
        signature=None,
        default_provider="anthropic",
        default_model="claude-test",
        status="canonical",
        doorwords=None,
        horizon_minutes=None,
        mischief_range=None,
        dismissal_protocol=None,
        ritual_twin_id=None,
        current_version_id="version-id",
        created_at=now,
        updated_at=now,
    )
    version = PromptVersion(
        id="version-id",
        prompt_id=prompt.id,
        parent_version_id=None,
        name=prompt.name,
        gloss=prompt.gloss,
        core=prompt.core,
        signature=prompt.signature,
        default_provider=prompt.default_provider,
        default_model=prompt.default_model,
        status=prompt.status,
        doorwords=prompt.doorwords,
        horizon_minutes=prompt.horizon_minutes,
        mischief_range=prompt.mischief_range,
        dismissal_protocol=prompt.dismissal_protocol,
        ritual_twin_id=prompt.ritual_twin_id,
        note="initial",
        created_at=now,
    )
    buddy = Buddy(
        id="buddy-id",
        name="Buddy",
        screen_name="buddy",
        provider_id="anthropic",
        model="claude-test",
        prompt_id=prompt.id,
        prompt_version_id=version.id,
        created_at=now,
        updated_at=now,
    )

    assert buddy.prompt_version_id == version.id
    assert version.core == "Be precise."


def test_buddy_memory_type_tracks_visible_memory_state() -> None:
    now = datetime.now(UTC)
    memory = BuddyMemory(
        buddy_id="buddy-id",
        memory_text="Standing decision.",
        enabled=True,
        suppress_injection=False,
        watermark_created_at="2026-06-13T00:00:00+00:00",
        watermark_message_id="message-id",
        updated_at=now,
    )

    assert memory.memory_text == "Standing decision."
    assert memory.enabled is True
    assert memory.suppress_injection is False


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
    metadata = ProviderResponseMetadata(
        model="claude-reported",
        response_id="response-id",
    )
    chunk = StreamChunk(
        text="",
        done=True,
        usage=usage,
        response_metadata=metadata,
    )

    assert config.kind == "anthropic"
    assert chunk.done is True
    assert chunk.usage == usage
    assert chunk.response_metadata == metadata


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


def test_estimate_cost_usd_applies_prompt_cache_multipliers() -> None:
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=500_000,
        model="model-a",
        cache_creation_5m_input_tokens=1_000_000,
        cache_creation_1h_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    rate_card = {"model-a": ModelPricing(input_per_mtok=4.0, output_per_mtok=20.0)}

    assert estimate_cost_usd(usage, rate_card) == 27.4


def test_estimate_cost_usd_returns_none_for_unknown_models() -> None:
    usage = TokenUsage(input_tokens=1, output_tokens=1, model="unknown")

    assert estimate_cost_usd(usage, {}) is None


def test_load_rate_card_reads_vendored_pricing_snapshot() -> None:
    rate_card = load_rate_card()

    assert rate_card["gpt-5"] == ModelPricing(
        input_per_mtok=1.25,
        output_per_mtok=10.0,
    )
    assert "mistral-small-2603" not in rate_card
