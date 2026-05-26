import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from aol_llm.core.errors import (
    AuthError,
    NetworkError,
    RateLimitError,
    UnknownProviderError,
)
from aol_llm.core.types import Message, ProviderConfig, StreamChunk
from aol_llm.providers.anthropic import ANTHROPIC_MESSAGES_URL, AnthropicProvider
from aol_llm.providers.base import Provider
from aol_llm.providers.openai_compat import OpenAICompatibleProvider
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
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
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
    payload = json.loads(route.calls.last.request.content)
    assert payload["system"] == "You are concise."
    assert payload["messages"] == [{"role": "user", "content": "hello"}]


@respx.mock
@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_text_and_usage() -> None:
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

    chunks = await collect(provider)

    assert [chunk.text for chunk in chunks] == ["hi", ""]
    assert chunks[-1].done is True
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 11
    assert chunks[-1].usage.output_tokens == 13
    payload = json.loads(route.calls.last.request.content)
    assert payload["messages"] == [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "hello"},
    ]
    assert payload["stream_options"] == {"include_usage": True}


@respx.mock
@pytest.mark.asyncio
async def test_openai_api_uses_max_completion_tokens() -> None:
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
    provider = OpenAICompatibleProvider(config=openai_api_config(), api_key="test-key")

    await collect(provider)

    payload = json.loads(route.calls.last.request.content)
    assert payload["max_completion_tokens"] == 4096
    assert payload["messages"] == [
        {"role": "developer", "content": "You are concise."},
        {"role": "user", "content": "hello"},
    ]
    assert "temperature" not in payload
    assert "max_tokens" not in payload


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
