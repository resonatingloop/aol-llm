import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from aol_llm.core.errors import (
    AuthError,
    ContentFilterError,
    NetworkError,
    RateLimitError,
    UnknownProviderError,
)
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd
from aol_llm.core.types import Message, ProviderConfig, StreamChunk
from aol_llm.providers.anthropic import ANTHROPIC_MESSAGES_URL, AnthropicProvider
from aol_llm.providers.base import Provider
from aol_llm.providers.openai_compat import OpenAICompatibleProvider
from aol_llm.providers.openai_responses import OpenAIResponseOptions
from aol_llm.providers.registry import build_provider


def make_message() -> Message:
    return Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=datetime.now(UTC),
    )


def anthropic_config() -> ProviderConfig:
    return ProviderConfig(
        id="anthropic",
        kind="anthropic",
        display_name="Anthropic",
        base_url=None,
        keyring_service="aol-llm.anthropic",
        default_model="claude-sonnet-4-6",
        available_models=["claude-sonnet-4-6"],
    )


def anthropic_opus_config(model: str) -> ProviderConfig:
    return ProviderConfig(
        id="anthropic",
        kind="anthropic",
        display_name="Anthropic",
        base_url=None,
        keyring_service="aol-llm.anthropic",
        default_model=model,
        available_models=[model],
    )


def openai_config() -> ProviderConfig:
    return ProviderConfig(
        id="openai",
        kind="openai_compatible",
        display_name="OpenAI",
        base_url="https://api.openai.test/v1",
        keyring_service="aol-llm.openai",
        default_model="gpt-test",
        available_models=["gpt-test"],
    )


def openai_api_config() -> ProviderConfig:
    return ProviderConfig(
        id="openai",
        kind="openai_compatible",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        keyring_service="aol-llm.openai",
        default_model="gpt-5",
        available_models=["gpt-5"],
    )


async def collect(provider: Provider) -> list[StreamChunk]:
    messages = [make_message()]
    return [
        chunk
        async for chunk in provider.stream(
            messages=messages,
            system="You are concise.",
            model=provider.config.default_model,
        )
    ]


def sse(*events: dict[str, object]) -> str:
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events)


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_streams_text_and_usage() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg-provider-123",
                        "model": "claude-reported",
                        "usage": {"input_tokens": 7},
                    },
                },
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(config=anthropic_config(), api_key="test-key")

    chunks = await collect(provider)

    assert [chunk.text for chunk in chunks] == ["hi", ""]
    assert chunks[-1].done is True
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 7
    assert chunks[-1].usage.output_tokens == 5
    assert chunks[-1].response_metadata is not None
    assert chunks[-1].response_metadata.model == "claude-reported"
    assert chunks[-1].response_metadata.response_id == "msg-provider-123"
    payload = json.loads(route.calls.last.request.content)
    assert payload["system"] == "You are concise."
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["temperature"] == 1.0


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_opus_4_8_uses_adaptive_thinking_without_temperature() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
                {"type": "content_block_delta", "delta": {"thinking": "hidden"}},
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_opus_config("claude-opus-4-8"),
        api_key="test-key",
    )

    chunks = await collect(provider)

    assert [chunk.text for chunk in chunks] == ["hi", ""]
    payload = json.loads(route.calls.last.request.content)
    assert payload["thinking"] == {"type": "adaptive"}
    assert "temperature" not in payload


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_adds_5m_prompt_cache_control_when_enabled() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 7,
                            "cache_creation_input_tokens": 11,
                            "cache_read_input_tokens": 13,
                        }
                    },
                },
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_config(),
        api_key="test-key",
        prompt_cache_ttl="5m",
    )

    chunks = await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["cache_control"] == {"type": "ephemeral"}
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.cache_creation_5m_input_tokens == 11
    assert chunks[-1].usage.cache_creation_1h_input_tokens == 0
    assert chunks[-1].usage.cache_read_input_tokens == 13


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_adds_1h_prompt_cache_control_and_usage() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 7,
                            "cache_creation_input_tokens": 24,
                            "cache_read_input_tokens": 13,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 11,
                                "ephemeral_1h_input_tokens": 13,
                            },
                        }
                    },
                },
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_config(),
        api_key="test-key",
        prompt_cache_ttl="1h",
    )

    chunks = await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.cache_creation_5m_input_tokens == 11
    assert chunks[-1].usage.cache_creation_1h_input_tokens == 13
    assert chunks[-1].usage.cache_read_input_tokens == 13


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_attributes_aggregate_usage_to_configured_ttl() -> (
    None
):
    respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 7,
                            "cache_creation_input_tokens": 24,
                            "cache_read_input_tokens": 13,
                        }
                    },
                },
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_config(),
        api_key="test-key",
        stable_prefix_cache_ttl="1h",
    )

    chunks = await collect(provider)

    usage = chunks[-1].usage
    assert usage is not None
    assert usage.cache_creation_5m_input_tokens == 0
    assert usage.cache_creation_1h_input_tokens == 24
    assert usage.cache_read_input_tokens == 13
    rate_card = {usage.model: ModelPricing(input_per_mtok=4.0, output_per_mtok=20.0)}
    assert estimate_cost_usd(usage, rate_card) == pytest.approx(0.0003252)


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_rejects_inconsistent_cache_usage() -> None:
    respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 7,
                            "cache_creation_input_tokens": 24,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 11,
                                "ephemeral_1h_input_tokens": 12,
                            },
                        }
                    },
                },
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_config(),
        api_key="test-key",
        prompt_cache_ttl="1h",
    )

    with pytest.raises(UnknownProviderError, match="does not match TTL breakdown"):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_caches_stable_system_and_history_prefix() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {"input_tokens": 7, "service_tier": "standard"}
                    },
                },
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 5},
                },
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_config(),
        api_key="test-key",
        stable_prefix_cache_ttl="1h",
        effort="high",
        request_timeout_seconds=300,
    )
    messages = [
        make_message(),
        Message(
            id="assistant-message",
            conversation_id="conversation-id",
            role="assistant",
            content="prior answer",
            created_at=datetime.now(UTC),
        ),
        Message(
            id="current-trigger",
            conversation_id="conversation-id",
            role="user",
            content="new question\n\n[Room turn instruction]\nRespond once.",
            created_at=datetime.now(UTC),
        ),
    ]

    chunks = [
        chunk
        async for chunk in provider.stream(
            messages=messages,
            system="Stable persona and room instructions.",
            model="claude-fable-5",
        )
    ]

    assert chunks[-1].done is True
    assert chunks[-1].response_metadata is not None
    assert chunks[-1].response_metadata.termination_reason == "end_turn"
    assert chunks[-1].response_metadata.service_tier == "standard"
    payload = json.loads(route.calls.last.request.content)
    assert "cache_control" not in payload
    assert "thinking" not in payload
    assert payload["output_config"] == {"effort": "high"}
    assert "temperature" not in payload
    assert payload["system"] == [
        {
            "type": "text",
            "text": "Stable persona and room instructions.",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    assert payload["messages"] == [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "prior answer",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
        },
        {
            "role": "user",
            "content": "new question\n\n[Room turn instruction]\nRespond once.",
        },
    ]


def test_anthropic_cache_strategies_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        AnthropicProvider(
            config=anthropic_config(),
            api_key="test-key",
            prompt_cache_ttl="5m",
            stable_prefix_cache_ttl="1h",
        )


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_opus_4_7_omits_temperature() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_opus_config("claude-opus-4-7"),
        api_key="test-key",
    )

    await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert "thinking" not in payload
    assert "temperature" not in payload


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_fable_uses_effort_cache_and_omits_temperature() -> None:
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 5}},
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_opus_config("claude-fable-5"),
        api_key="test-key",
        stable_prefix_cache_ttl="1h",
        effort="high",
        request_timeout_seconds=180,
    )

    await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["model"] == "claude-fable-5"
    assert payload["max_tokens"] == 4096
    assert payload["stream"] is True
    assert payload["output_config"] == {"effort": "high"}
    assert payload["system"] == [
        {
            "type": "text",
            "text": "You are concise.",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    assert "temperature" not in payload


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_fable_refusal_maps_to_content_filter_error() -> None:
    respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "refusal"},
                    "usage": {"output_tokens": 0},
                },
                {"type": "message_stop"},
            ),
        )
    )
    provider = AnthropicProvider(
        config=anthropic_opus_config("claude-fable-5"),
        api_key="test-key",
    )

    with pytest.raises(ContentFilterError):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_text_and_usage() -> None:
    route = respx.post("https://api.openai.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "id": "chatcmpl-provider-123",
                    "model": "gpt-reported",
                    "choices": [{"delta": {"content": "hi"}}],
                },
                {
                    "id": "chatcmpl-provider-123",
                    "model": "gpt-reported",
                    "choices": [],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 13},
                },
            )
            + "data: [DONE]\n\n",
        )
    )
    provider = OpenAICompatibleProvider(config=openai_config(), api_key="test-key")

    chunks = await collect(provider)

    assert [chunk.text for chunk in chunks] == ["hi", ""]
    assert chunks[-1].done is True
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 11
    assert chunks[-1].usage.output_tokens == 13
    assert chunks[-1].response_metadata is not None
    assert chunks[-1].response_metadata.model == "gpt-reported"
    assert chunks[-1].response_metadata.response_id == "chatcmpl-provider-123"
    payload = json.loads(route.calls.last.request.content)
    assert payload["messages"] == [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "hello"},
    ]
    assert payload["stream_options"] == {"include_usage": True}


@respx.mock
@pytest.mark.asyncio
async def test_openai_api_uses_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    seen_timeouts: list[float] = []

    def recording_client(*, timeout: float) -> httpx.AsyncClient:
        seen_timeouts.append(timeout)
        return real_client(timeout=timeout)

    monkeypatch.setattr(
        "aol_llm.providers.openai_compat.httpx.AsyncClient",
        recording_client,
    )
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"choices": [{"delta": {"content": "hi"}}]},
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 13},
                },
            )
            + "data: [DONE]\n\n",
        )
    )
    provider = OpenAICompatibleProvider(
        config=openai_api_config(),
        api_key="test-key",
        request_timeout_seconds=180,
    )

    await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["max_completion_tokens"] == 4096
    assert payload["messages"] == [
        {"role": "developer", "content": "You are concise."},
        {"role": "user", "content": "hello"},
    ]
    assert "temperature" not in payload
    assert "max_tokens" not in payload
    assert seen_timeouts == [180]


@respx.mock
@pytest.mark.asyncio
async def test_openai_api_responses_supports_verbosity_and_prompt_caching() -> None:
    route = respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"type": "response.output_text.delta", "delta": "hi"},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp-provider-123",
                        "model": "gpt-5.6-sol",
                        "status": "completed",
                        "service_tier": "default",
                        "usage": {
                            "input_tokens": 17,
                            "input_tokens_details": {
                                "cached_tokens": 7,
                                "cache_write_tokens": 5,
                            },
                            "output_tokens": 19,
                        },
                    },
                },
            ),
        )
    )
    provider = OpenAICompatibleProvider(
        config=openai_api_config(),
        api_key="test-key",
        response_options=OpenAIResponseOptions(
            text_verbosity="medium",
            prompt_cache_key="discordant:sol",
            reasoning_effort="medium",
            safety_identifier="hmac-user-id",
            request_timeout_seconds=180,
        ),
    )

    chunks = await collect(provider)

    assert [chunk.text for chunk in chunks] == ["hi", ""]
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 5
    assert chunks[-1].usage.cache_read_input_tokens == 7
    assert chunks[-1].usage.cache_write_input_tokens == 5
    assert chunks[-1].usage.output_tokens == 19
    assert chunks[-1].response_metadata is not None
    assert chunks[-1].response_metadata.model == "gpt-5.6-sol"
    assert chunks[-1].response_metadata.response_id == "resp-provider-123"
    assert chunks[-1].response_metadata.termination_reason == "completed"
    assert chunks[-1].response_metadata.service_tier == "default"
    payload = json.loads(route.calls.last.request.content)
    assert payload == {
        "model": "gpt-5",
        "input": [{"role": "user", "content": "hello"}],
        "stream": True,
        "max_output_tokens": 4096,
        "store": False,
        "instructions": "You are concise.",
        "text": {"verbosity": "medium"},
        "prompt_cache_key": "discordant:sol",
        "reasoning": {"effort": "medium"},
        "safety_identifier": "hmac-user-id",
    }


@respx.mock
@pytest.mark.asyncio
async def test_openai_responses_preserves_unreported_cache_details_as_none() -> None:
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "response-id",
                        "model": "gpt-5.6",
                        "usage": {"input_tokens": 17, "output_tokens": 19},
                    },
                },
            ),
        )
    )
    provider = OpenAICompatibleProvider(
        config=openai_api_config(),
        api_key="test-key",
        response_options=OpenAIResponseOptions(text_verbosity="medium"),
    )

    chunks = await collect(provider)

    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 17
    assert chunks[-1].usage.cache_read_input_tokens is None
    assert chunks[-1].usage.cache_write_input_tokens is None


@pytest.mark.asyncio
async def test_responses_options_reject_non_openai_compatible_host() -> None:
    provider = OpenAICompatibleProvider(
        config=openai_config(),
        api_key="test-key",
        response_options=OpenAIResponseOptions(text_verbosity="medium"),
    )

    with pytest.raises(UnknownProviderError, match="api.openai.com"):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_non_openai_compatible_provider_keeps_max_tokens() -> None:
    route = respx.post("https://api.openai.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=sse(
                {"choices": [{"delta": {"content": "hi"}}]},
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 13},
                },
            )
            + "data: [DONE]\n\n",
        )
    )
    provider = OpenAICompatibleProvider(config=openai_config(), api_key="test-key")

    await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["max_tokens"] == 4096
    assert payload["temperature"] == 1.0
    assert "max_completion_tokens" not in payload


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [(401, AuthError), (429, RateLimitError)],
)
async def test_anthropic_provider_maps_http_errors(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    respx.post(ANTHROPIC_MESSAGES_URL).mock(return_value=httpx.Response(status_code))
    provider = AnthropicProvider(config=anthropic_config(), api_key="test-key")

    with pytest.raises(expected_error):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [(401, AuthError), (429, RateLimitError)],
)
async def test_openai_compatible_provider_maps_http_errors(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    respx.post("https://api.openai.test/v1/chat/completions").mock(
        return_value=httpx.Response(status_code)
    )
    provider = OpenAICompatibleProvider(config=openai_config(), api_key="test-key")

    with pytest.raises(expected_error):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_provider_http_400_includes_bounded_error_body() -> None:
    respx.post("https://api.openai.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "message": "Unsupported parameter: max_tokens",
                    "type": "invalid_request_error",
                }
            },
        )
    )
    provider = OpenAICompatibleProvider(config=openai_config(), api_key="test-key")

    with pytest.raises(UnknownProviderError, match="Unsupported parameter: max_tokens"):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_anthropic_provider_maps_network_errors() -> None:
    respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=httpx.ConnectError("boom"))
    provider = AnthropicProvider(config=anthropic_config(), api_key="test-key")

    with pytest.raises(NetworkError):
        await collect(provider)


@respx.mock
@pytest.mark.asyncio
async def test_openai_compatible_provider_maps_network_errors() -> None:
    respx.post("https://api.openai.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    provider = OpenAICompatibleProvider(config=openai_config(), api_key="test-key")

    with pytest.raises(NetworkError):
        await collect(provider)


def test_registry_builds_provider_family() -> None:
    assert isinstance(build_provider(anthropic_config(), "key"), AnthropicProvider)
    assert isinstance(build_provider(openai_config(), "key"), OpenAICompatibleProvider)
