from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from aol_llm.core.errors import AuthError, NetworkError, RateLimitError
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)
from aol_llm.providers.base import Provider


class FakeProvider:
    config = ProviderConfig(
        id="fake",
        kind="anthropic",
        display_name="Fake",
        base_url=None,
        keyring_service=None,
        default_model="fake-model",
        available_models=["fake-model"],
    )

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        del messages, system, max_output_tokens, temperature
        yield StreamChunk(text="hello", done=False)
        yield StreamChunk(
            text="",
            done=True,
            usage=TokenUsage(input_tokens=3, output_tokens=5, model=model),
        )


class ErrorProvider:
    def __init__(self, error: Exception) -> None:
        self.config = FakeProvider.config
        self._error = error

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        del messages, system, model, max_output_tokens, temperature
        raise self._error
        yield StreamChunk(text="", done=True)


def make_message() -> Message:
    return Message(
        id="message-id",
        conversation_id="conversation-id",
        role="user",
        content="hello",
        created_at=datetime.now(UTC),
    )


async def collect_stream(provider: Provider) -> list[StreamChunk]:
    messages = [make_message()]
    original_messages = list(messages)
    chunks = [
        chunk
        async for chunk in provider.stream(
            messages=messages,
            system="You are concise.",
            model=provider.config.default_model,
        )
    ]

    assert messages == original_messages
    return chunks


@pytest.mark.asyncio
async def test_provider_stream_contract_completes_with_usage() -> None:
    chunks = await collect_stream(FakeProvider())

    assert chunks
    assert chunks[-1].done is True
    assert chunks[-1].usage is not None
    assert all(chunk.done is False for chunk in chunks[:-1])
    assert all(chunk.usage is None for chunk in chunks[:-1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AuthError("missing api key"),
        RateLimitError("rate limited"),
        NetworkError("connection failed"),
    ],
)
async def test_provider_stream_contract_raises_provider_errors(
    error: Exception,
) -> None:
    with pytest.raises(type(error)):
        await collect_stream(ErrorProvider(error))
