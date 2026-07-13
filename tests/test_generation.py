from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from aol_llm.core.errors import ProviderError, RateLimitError, UnknownProviderError
from aol_llm.core.pricing import ModelPricing
from aol_llm.core.requests import NormalizedChatRequest, normalize_chat_request
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    ProviderResponseMetadata,
    StreamChunk,
    TokenUsage,
)
from aol_llm.generation import ProviderFactory, generate
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import AnthropicCacheTTL


def provider_config() -> ProviderConfig:
    return ProviderConfig(
        id="anthropic",
        kind="anthropic",
        display_name="Anthropic",
        base_url=None,
        keyring_service="aol-llm.anthropic",
        default_model="requested-model",
        available_models=["requested-model"],
    )


def request() -> NormalizedChatRequest:
    message = Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=datetime.now(UTC),
    )
    return normalize_chat_request(
        [message],
        "Be concise.",
        "requested-model",
        max_output_tokens=321,
        temperature=0.4,
    )


class FakeProvider:
    def __init__(
        self,
        chunks: tuple[StreamChunk, ...],
        error: ProviderError | None = None,
    ) -> None:
        self.config = provider_config()
        self._chunks = chunks
        self._error = error

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        assert [message.content for message in messages] == ["hello"]
        assert (system, model) == ("Be concise.", "requested-model")
        assert (max_output_tokens, temperature) == (321, 0.4)
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk


def successful_provider() -> FakeProvider:
    return FakeProvider(
        (
            StreamChunk(text="hel", done=False),
            StreamChunk(
                text="lo",
                done=True,
                usage=TokenUsage(10, 20, "requested-model"),
                response_metadata=ProviderResponseMetadata(
                    model="reported-model",
                    response_id="provider-response-id",
                    termination_reason="end_turn",
                    service_tier="standard",
                ),
            ),
        )
    )


def factory_for(provider: Provider) -> ProviderFactory:
    def factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: AnthropicCacheTTL | None,
    ) -> Provider:
        assert config == provider.config
        assert api_key == "secret"
        assert prompt_cache_ttl is None
        return provider

    return factory


@pytest.mark.asyncio
async def test_generate_collects_text_usage_cost_and_provenance() -> None:
    result = await generate(
        provider_config(),
        "secret",
        request(),
        provider_factory=factory_for(successful_provider()),
        rate_card={"requested-model": ModelPricing(1.0, 2.0)},
    )

    assert result.text == "hello"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (10, 20)
    assert result.cost_usd == 0.00005
    assert (result.provider_id, result.provider_kind) == ("anthropic", "anthropic")
    assert result.requested_model == "requested-model"
    assert result.reported_model == "reported-model"
    assert result.provider_response_id == "provider-response-id"
    assert result.termination_reason == "end_turn"
    assert result.service_tier == "standard"


@pytest.mark.asyncio
async def test_generate_keeps_unknown_model_cost_unpriced() -> None:
    result = await generate(
        provider_config(),
        "secret",
        request(),
        provider_factory=factory_for(successful_provider()),
        rate_card={},
    )

    assert result.cost_usd is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "error", "match"),
    [
        (
            FakeProvider((), RateLimitError("rate limited")),
            RateLimitError,
            "rate limited",
        ),
        (
            FakeProvider((StreamChunk(text="partial", done=False),)),
            UnknownProviderError,
            "without a final chunk",
        ),
        (
            FakeProvider((StreamChunk(text="missing usage", done=True),)),
            UnknownProviderError,
            "missing usage",
        ),
    ],
)
async def test_generate_propagates_or_rejects_invalid_streams(
    provider: Provider,
    error: type[ProviderError],
    match: str,
) -> None:
    with pytest.raises(error, match=match):
        await generate(
            provider_config(),
            "secret",
            request(),
            provider_factory=factory_for(provider),
            rate_card={},
        )
