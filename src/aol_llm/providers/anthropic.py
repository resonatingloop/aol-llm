"""Anthropic Messages API provider adapter."""

from collections.abc import AsyncIterator
from typing import Literal

import httpx

from aol_llm.core.errors import AuthError, ContentFilterError, UnknownProviderError
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    ProviderResponseMetadata,
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
AnthropicEffort = Literal["low", "medium", "high", "xhigh", "max"]


class AnthropicProvider:
    def __init__(
        self,
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: AnthropicCacheTTL | None = None,
        stable_prefix_cache_ttl: AnthropicCacheTTL | None = None,
        effort: AnthropicEffort | None = None,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        if prompt_cache_ttl is not None and stable_prefix_cache_ttl is not None:
            raise ValueError(
                "automatic and stable-prefix caching are mutually exclusive"
            )
        self.config = config
        self._api_key = api_key
        self._prompt_cache_ttl = prompt_cache_ttl
        self._stable_prefix_cache_ttl = stable_prefix_cache_ttl
        self._effort = effort
        self._request_timeout_seconds = request_timeout_seconds

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
            "messages": _payload_messages(
                messages,
                self._stable_prefix_cache_ttl,
            ),
        }
        if _supports_adaptive_thinking(model):
            payload["thinking"] = {"type": "adaptive"}
        if not _rejects_sampling_parameters(model):
            payload["temperature"] = temperature
        if self._effort is not None:
            payload["output_config"] = {"effort": self._effort}
        if self._prompt_cache_ttl is not None:
            payload["cache_control"] = _cache_control(self._prompt_cache_ttl)
        if system is not None:
            if self._stable_prefix_cache_ttl is None:
                payload["system"] = system
            else:
                payload["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": _cache_control(self._stable_prefix_cache_ttl),
                    }
                ]

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        input_tokens: int | None = None
        output_tokens: int | None = None
        reported_model: str | None = None
        response_id: str | None = None
        cache_creation_5m_input_tokens = 0
        cache_creation_1h_input_tokens = 0
        cache_read_input_tokens = 0
        termination_reason: str | None = None
        service_tier: str | None = None

        try:
            async with httpx.AsyncClient(
                timeout=self._request_timeout_seconds
            ) as client:
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
                            message = event.get("message", {})
                            reported_model = _optional_str(message.get("model"))
                            response_id = _optional_str(message.get("id"))
                            usage = message.get("usage", {})
                            reported_input_tokens = _optional_int(
                                usage.get("input_tokens")
                            )
                            if reported_input_tokens is not None:
                                input_tokens = reported_input_tokens
                            reported_output_tokens = _optional_int(
                                usage.get("output_tokens")
                            )
                            if reported_output_tokens is not None:
                                output_tokens = reported_output_tokens
                            service_tier = (
                                _optional_str(usage.get("service_tier")) or service_tier
                            )
                            (
                                cache_creation_5m_input_tokens,
                                cache_creation_1h_input_tokens,
                                cache_read_input_tokens,
                            ) = _merge_cache_usage(
                                usage,
                                configured_ttl=(
                                    self._prompt_cache_ttl
                                    or self._stable_prefix_cache_ttl
                                ),
                                cache_creation_5m_input_tokens=(
                                    cache_creation_5m_input_tokens
                                ),
                                cache_creation_1h_input_tokens=(
                                    cache_creation_1h_input_tokens
                                ),
                                cache_read_input_tokens=cache_read_input_tokens,
                            )
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
                            if isinstance(delta, dict):
                                termination_reason = (
                                    _optional_str(delta.get("stop_reason"))
                                    or termination_reason
                                )
                            usage = event.get("usage", {})
                            reported_output_tokens = _optional_int(
                                usage.get("output_tokens")
                            )
                            if reported_output_tokens is not None:
                                output_tokens = reported_output_tokens
                            service_tier = (
                                _optional_str(usage.get("service_tier")) or service_tier
                            )
                            (
                                cache_creation_5m_input_tokens,
                                cache_creation_1h_input_tokens,
                                cache_read_input_tokens,
                            ) = _merge_cache_usage(
                                usage,
                                configured_ttl=(
                                    self._prompt_cache_ttl
                                    or self._stable_prefix_cache_ttl
                                ),
                                cache_creation_5m_input_tokens=(
                                    cache_creation_5m_input_tokens
                                ),
                                cache_creation_1h_input_tokens=(
                                    cache_creation_1h_input_tokens
                                ),
                                cache_read_input_tokens=cache_read_input_tokens,
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
                                response_metadata=ProviderResponseMetadata(
                                    model=reported_model,
                                    response_id=response_id,
                                    termination_reason=termination_reason,
                                    service_tier=service_tier,
                                ),
                            )
                            return
        except httpx.RequestError as error:
            raise translate_httpx_error(error) from error

        raise UnknownProviderError("Anthropic stream ended without final usage")


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _merge_cache_usage(
    usage: object,
    *,
    configured_ttl: AnthropicCacheTTL | None,
    cache_creation_5m_input_tokens: int,
    cache_creation_1h_input_tokens: int,
    cache_read_input_tokens: int,
) -> tuple[int, int, int]:
    if not isinstance(usage, dict):
        return (
            cache_creation_5m_input_tokens,
            cache_creation_1h_input_tokens,
            cache_read_input_tokens,
        )

    reported_read = _optional_int(usage.get("cache_read_input_tokens"))
    if reported_read is not None:
        cache_read_input_tokens = reported_read

    aggregate_creation = _optional_int(usage.get("cache_creation_input_tokens"))
    cache_creation = usage.get("cache_creation")
    if isinstance(cache_creation, dict):
        reported_5m_value = _optional_int(
            cache_creation.get("ephemeral_5m_input_tokens")
        )
        reported_1h_value = _optional_int(
            cache_creation.get("ephemeral_1h_input_tokens")
        )
    else:
        reported_5m_value = None
        reported_1h_value = None

    if reported_5m_value is not None or reported_1h_value is not None:
        reported_5m = reported_5m_value or 0
        reported_1h = reported_1h_value or 0
        if (
            aggregate_creation is not None
            and aggregate_creation != reported_5m + reported_1h
        ):
            raise UnknownProviderError(
                "Anthropic cache-creation usage total does not match TTL breakdown"
            )
        cache_creation_5m_input_tokens = reported_5m
        cache_creation_1h_input_tokens = reported_1h
    elif aggregate_creation is not None:
        if configured_ttl == "1h":
            cache_creation_5m_input_tokens = 0
            cache_creation_1h_input_tokens = aggregate_creation
        else:
            cache_creation_5m_input_tokens = aggregate_creation
            cache_creation_1h_input_tokens = 0

    return (
        cache_creation_5m_input_tokens,
        cache_creation_1h_input_tokens,
        cache_read_input_tokens,
    )


def _payload_messages(
    messages: list[Message],
    stable_prefix_cache_ttl: AnthropicCacheTTL | None,
) -> list[dict[str, object]]:
    payload_messages: list[dict[str, object]] = [
        {"role": message.role, "content": message.content} for message in messages
    ]
    if stable_prefix_cache_ttl is None or len(messages) < 2:
        return payload_messages

    stable_index = len(messages) - 2
    stable_message = messages[stable_index]
    payload_messages[stable_index] = {
        "role": stable_message.role,
        "content": [
            {
                "type": "text",
                "text": stable_message.content,
                "cache_control": _cache_control(stable_prefix_cache_ttl),
            }
        ],
    }
    return payload_messages


def _cache_control(ttl: AnthropicCacheTTL) -> dict[str, str]:
    cache_control = {"type": "ephemeral"}
    if ttl == "1h":
        cache_control["ttl"] = ttl
    return cache_control


def _supports_adaptive_thinking(model: str) -> bool:
    return model == "claude-opus-4-8"


def _rejects_sampling_parameters(model: str) -> bool:
    return model in {"claude-fable-5", "claude-opus-4-8", "claude-opus-4-7"}
