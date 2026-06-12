"""Provider protocol shared by all provider adapters."""

from collections.abc import AsyncIterator
from typing import Protocol

from aol_llm.core.types import Message, PromptCacheControl, ProviderConfig, StreamChunk


class Provider(Protocol):
    config: ProviderConfig

    def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
        prompt_cache: PromptCacheControl | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream normalized chunks from a provider."""
