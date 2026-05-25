"""Shared HTTP helpers for provider adapters."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from aol_llm.core.errors import (
    AuthError,
    ContentFilterError,
    ContextLengthError,
    NetworkError,
    RateLimitError,
    UnknownProviderError,
)


def parse_sse_json(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None

    data = line.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return None

    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise UnknownProviderError("provider returned non-object stream data")
    return parsed


async def iter_sse_json(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        parsed = parse_sse_json(line)
        if parsed is not None:
            yield parsed


async def raise_for_provider_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return

    body = await response.aread()
    text = body.decode(errors="replace").lower()
    if response.status_code in {401, 403}:
        raise AuthError("provider rejected authentication")
    if response.status_code == 429:
        raise RateLimitError("provider rate limit exceeded")
    if "context" in text and "length" in text:
        raise ContextLengthError("provider context length exceeded")
    if "content_filter" in text or "safety" in text or "policy" in text:
        raise ContentFilterError("provider refused the request")
    raise UnknownProviderError(
        f"provider returned HTTP {response.status_code}: {_body_excerpt(body)}"
    )


def translate_httpx_error(error: httpx.RequestError) -> NetworkError:
    del error
    return NetworkError("provider request failed")


def _body_excerpt(body: bytes, limit: int = 240) -> str:
    text = body.decode(errors="replace").strip()
    text = " ".join(text.split())
    if not text:
        return "empty response body"
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text
