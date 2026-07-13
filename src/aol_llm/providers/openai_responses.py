"""Opt-in OpenAI Responses API streaming for provider-specific controls."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import httpx

from aol_llm.core.errors import UnknownProviderError
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

TextVerbosity = Literal["low", "medium", "high"]
OpenAIReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class OpenAIResponseOptions:
    """Controls available only on OpenAI's Responses API."""

    text_verbosity: TextVerbosity | None = None
    prompt_cache_key: str | None = None
    reasoning_effort: OpenAIReasoningEffort | None = None
    safety_identifier: str | None = None
    store: bool = False
    request_timeout_seconds: float = 60.0


async def stream_openai_response(
    config: ProviderConfig,
    api_key: str | None,
    options: OpenAIResponseOptions,
    messages: list[Message],
    system: str | None,
    model: str,
    max_output_tokens: int,
) -> AsyncIterator[StreamChunk]:
    if config.base_url is None:
        raise UnknownProviderError("OpenAI Responses API requires a base_url")

    payload: dict[str, object] = {
        "model": model,
        "input": [
            {"role": message.role, "content": message.content} for message in messages
        ],
        "stream": True,
        "max_output_tokens": max_output_tokens,
        "store": options.store,
    }
    if system is not None:
        payload["instructions"] = system
    if options.text_verbosity is not None:
        payload["text"] = {"verbosity": options.text_verbosity}
    if options.prompt_cache_key is not None:
        payload["prompt_cache_key"] = options.prompt_cache_key
    if options.reasoning_effort is not None:
        payload["reasoning"] = {"effort": options.reasoning_effort}
    if options.safety_identifier is not None:
        payload["safety_identifier"] = options.safety_identifier

    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=options.request_timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{config.base_url.rstrip('/')}/responses",
                headers=headers,
                json=payload,
            ) as response:
                await raise_for_provider_status(response)
                async for event in iter_sse_json(response):
                    event_type = event.get("type")
                    if event_type == "response.output_text.delta":
                        text = event.get("delta")
                        if isinstance(text, str) and text:
                            yield StreamChunk(text=text, done=False)
                        continue
                    if event_type in {"response.completed", "response.incomplete"}:
                        completed = event.get("response")
                        if not isinstance(completed, dict):
                            raise UnknownProviderError(
                                "OpenAI response completion was missing response data"
                            )
                        usage = completed.get("usage")
                        if not isinstance(usage, dict):
                            raise UnknownProviderError(
                                "OpenAI response was missing token usage"
                            )
                        input_tokens = _required_int(usage.get("input_tokens"))
                        input_details = usage.get("input_tokens_details")
                        cache_read_input_tokens: int | None = None
                        cache_write_input_tokens: int | None = None
                        if isinstance(input_details, dict):
                            cache_read_input_tokens = _optional_int(
                                input_details.get("cached_tokens")
                            )
                            cache_write_input_tokens = _optional_int(
                                input_details.get("cache_write_tokens")
                            )
                        ordinary_input_tokens = (
                            input_tokens
                            - (cache_read_input_tokens or 0)
                            - (cache_write_input_tokens or 0)
                        )
                        if ordinary_input_tokens < 0:
                            raise UnknownProviderError(
                                "OpenAI cache token counts exceeded total input tokens"
                            )
                        incomplete_details = completed.get("incomplete_details")
                        incomplete_reason = (
                            _optional_str(incomplete_details.get("reason"))
                            if isinstance(incomplete_details, dict)
                            else None
                        )
                        fallback_reason = (
                            "incomplete"
                            if event_type == "response.incomplete"
                            else "completed"
                        )
                        yield StreamChunk(
                            text="",
                            done=True,
                            usage=TokenUsage(
                                input_tokens=ordinary_input_tokens,
                                output_tokens=_required_int(usage.get("output_tokens")),
                                model=model,
                                cache_read_input_tokens=cache_read_input_tokens,
                                cache_write_input_tokens=cache_write_input_tokens,
                            ),
                            response_metadata=ProviderResponseMetadata(
                                model=_optional_str(completed.get("model")),
                                response_id=_optional_str(completed.get("id")),
                                termination_reason=(
                                    incomplete_reason
                                    or _optional_str(completed.get("status"))
                                    or fallback_reason
                                ),
                                service_tier=_optional_str(
                                    completed.get("service_tier")
                                ),
                            ),
                        )
                        return
                    if event_type in {"error", "response.failed"}:
                        raise UnknownProviderError("OpenAI response stream failed")
    except httpx.RequestError as error:
        raise translate_httpx_error(error) from error

    raise UnknownProviderError("OpenAI response stream ended without final usage")


def _required_int(value: object) -> int:
    if not isinstance(value, int):
        raise UnknownProviderError("provider usage was missing token counts")
    return value


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
