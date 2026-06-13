"""Anthropic Messages API provider adapter."""

from collections.abc import AsyncIterator
from typing import Literal

import httpx

from aol_llm.core.errors import AuthError, ContentFilterError, UnknownProviderError
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)
from aol_llm.providers._http import (
    iter_sse_json,
    raise_for_provider_status,
    translate_httpx_error,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
AnthropicCacheTTL = Literal["5m", "1h"]


class AnthropicProvider:
    def __init__(
        self,
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: AnthropicCacheTTL | None = None,
    ) -> None:
        self.config = config
        self._api_key = api_key
        self._prompt_cache_ttl = prompt_cache_ttl

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        if not self._api_key:
            raise AuthError("missing Anthropic API key")

        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "stream": True,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        if _supports_adaptive_thinking(model):
            payload["thinking"] = {"type": "adaptive"}
        if not _rejects_sampling_parameters(model):
            payload["temperature"] = temperature
        if self._prompt_cache_ttl is not None:
            cache_control = {"type": "ephemeral"}
            if self._prompt_cache_ttl == "1h":
                cache_control["ttl"] = self._prompt_cache_ttl
            payload["cache_control"] = cache_control
        if system is not None:
            payload["system"] = system

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        input_tokens: int | None = None
        output_tokens: int | None = None
        cache_creation_5m_input_tokens = 0
        cache_creation_1h_input_tokens = 0
        cache_read_input_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    ANTHROPIC_MESSAGES_URL,
                    headers=headers,
                    json=payload,
                ) as response:
                    await raise_for_provider_status(response)
                    async for event in iter_sse_json(response):
                        event_type = event.get("type")
                        if event_type == "message_start":
                            usage = event.get("message", {}).get("usage", {})
                            input_tokens = _optional_int(usage.get("input_tokens"))
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                yield StreamChunk(text=text, done=False)
                        elif event_type == "message_delta":
                            delta = event.get("delta", {})
                            if (
                                isinstance(delta, dict)
                                and delta.get("stop_reason") == "refusal"
                            ):
                                raise ContentFilterError(
                                    "Anthropic refused the request"
                                )
                            usage = event.get("usage", {})
                            output_tokens = _optional_int(usage.get("output_tokens"))
                            cache_creation = usage.get("cache_creation")
                            if isinstance(cache_creation, dict):
                                cache_creation_5m_input_tokens = (
                                    _optional_int(
                                        cache_creation.get("ephemeral_5m_input_tokens")
                                    )
                                    or 0
                                )
                                cache_creation_1h_input_tokens = (
                                    _optional_int(
                                        cache_creation.get("ephemeral_1h_input_tokens")
                                    )
                                    or 0
                                )
                            else:
                                cache_creation_5m_input_tokens = (
                                    _optional_int(
                                        usage.get("cache_creation_input_tokens")
                                    )
                                    or 0
                                )
                            cache_read_input_tokens = (
                                _optional_int(usage.get("cache_read_input_tokens")) or 0
                            )
                        elif event_type == "message_stop":
                            if input_tokens is None or output_tokens is None:
                                raise UnknownProviderError(
                                    "Anthropic stream ended without usage"
                                )
                            yield StreamChunk(
                                text="",
                                done=True,
                                usage=TokenUsage(
                                    input_tokens=input_tokens,
                                    output_tokens=output_tokens,
                                    model=model,
                                    cache_creation_5m_input_tokens=cache_creation_5m_input_tokens,
                                    cache_creation_1h_input_tokens=cache_creation_1h_input_tokens,
                                    cache_read_input_tokens=cache_read_input_tokens,
                                ),
                            )
                            return
        except httpx.RequestError as error:
            raise translate_httpx_error(error) from error

        raise UnknownProviderError("Anthropic stream ended without final usage")


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _supports_adaptive_thinking(model: str) -> bool:
    return model == "claude-opus-4-8"


def _rejects_sampling_parameters(model: str) -> bool:
    return model in {"claude-opus-4-8", "claude-opus-4-7"}
