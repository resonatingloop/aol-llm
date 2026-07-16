"""OpenAI-compatible chat completions provider adapter."""

from collections.abc import AsyncIterator
from urllib.parse import urlparse

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
from aol_llm.providers.openai_responses import (
    OpenAIResponseOptions,
    stream_openai_response,
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: ProviderConfig,
        api_key: str | None,
        response_options: OpenAIResponseOptions | None = None,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self.config = config
        self._api_key = api_key
        self._response_options = response_options
        self._request_timeout_seconds = request_timeout_seconds

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        if self.config.base_url is None:
            raise UnknownProviderError("OpenAI-compatible provider requires a base_url")

        is_openai_api = _is_openai_api(self.config.base_url)
        if self._response_options is not None:
            if not is_openai_api:
                raise UnknownProviderError(
                    "OpenAI Responses options require the api.openai.com base URL"
                )
            async for chunk in stream_openai_response(
                config=self.config,
                api_key=self._api_key,
                options=self._response_options,
                messages=messages,
                system=system,
                model=model,
                max_output_tokens=max_output_tokens,
            ):
                yield chunk
            return

        payload_messages = []
        if system is not None:
            payload_messages.append(
                {
                    "role": "developer" if is_openai_api else "system",
                    "content": system,
                }
            )
        payload_messages.extend(
            {"role": message.role, "content": message.content} for message in messages
        )
        payload = {
            "model": model,
            "messages": payload_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if not is_openai_api:
            payload["temperature"] = temperature
        payload[_max_tokens_field(is_openai_api)] = max_output_tokens
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        reported_model: str | None = None
        response_id: str | None = None

        try:
            async with httpx.AsyncClient(
                timeout=self._request_timeout_seconds
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    await raise_for_provider_status(response)
                    async for event in iter_sse_json(response):
                        reported_model = (
                            _optional_str(event.get("model")) or reported_model
                        )
                        response_id = _optional_str(event.get("id")) or response_id
                        usage = event.get("usage")
                        if isinstance(usage, dict):
                            yield StreamChunk(
                                text="",
                                done=True,
                                usage=TokenUsage(
                                    input_tokens=_required_int(
                                        usage.get("prompt_tokens")
                                    ),
                                    output_tokens=_required_int(
                                        usage.get("completion_tokens")
                                    ),
                                    model=model,
                                ),
                                response_metadata=ProviderResponseMetadata(
                                    model=reported_model,
                                    response_id=response_id,
                                ),
                            )
                            return

                        for choice in event.get("choices", []):
                            delta = choice.get("delta", {})
                            text = delta.get("content")
                            if isinstance(text, str) and text:
                                yield StreamChunk(text=text, done=False)
        except httpx.RequestError as error:
            raise translate_httpx_error(error) from error

        raise UnknownProviderError("OpenAI-compatible stream ended without final usage")


def _required_int(value: object) -> int:
    if not isinstance(value, int):
        raise UnknownProviderError("provider usage was missing token counts")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _is_openai_api(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname
    return hostname == "api.openai.com"


def _max_tokens_field(is_openai_api: bool) -> str:
    return "max_completion_tokens" if is_openai_api else "max_tokens"
