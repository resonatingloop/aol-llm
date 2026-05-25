"""OpenAI-compatible chat completions provider adapter."""

from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.types import Message, ProviderConfig, StreamChunk, TokenUsage
from aol_llm.providers._http import (
    iter_sse_json,
    raise_for_provider_status,
    translate_httpx_error,
)


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig, api_key: str | None) -> None:
        self.config = config
        self._api_key = api_key

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

        payload_messages = []
        if system is not None:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(
            {"role": message.role, "content": message.content} for message in messages
        )
        payload = {
            "model": model,
            "messages": payload_messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        payload[_max_tokens_field(self.config.base_url)] = max_output_tokens
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    await raise_for_provider_status(response)
                    async for event in iter_sse_json(response):
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


def _max_tokens_field(base_url: str) -> str:
    hostname = urlparse(base_url).hostname
    if hostname == "api.openai.com":
        return "max_completion_tokens"
    return "max_tokens"
