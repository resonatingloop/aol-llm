import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from aol_llm.core.errors import AuthError, NetworkError, RateLimitError
from aol_llm.core.requests import normalize_chat_request
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)
from aol_llm.providers.base import Provider
from aol_llm.generation import generate


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


@pytest.mark.asyncio
async def test_generation_facade_propagates_cancellation() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    class BlockingProvider(FakeProvider):
        async def stream(
            self,
            messages: list[Message],
            system: str | None,
            model: str,
            max_output_tokens: int = 4096,
            temperature: float = 1.0,
        ) -> AsyncIterator[StreamChunk]:
            del messages, system, model, max_output_tokens, temperature
            started.set()
            try:
                await asyncio.sleep(3600)
            finally:
                stopped.set()
            yield StreamChunk(text="", done=True)

    provider = BlockingProvider()
    task = asyncio.create_task(
        generate(
            provider.config,
            None,
            normalize_chat_request(
                [make_message()], None, provider.config.default_model
            ),
            provider_factory=lambda config, api_key, cache_ttl: provider,
            rate_card={},
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
