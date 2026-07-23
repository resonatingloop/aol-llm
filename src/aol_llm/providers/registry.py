"""Provider adapter registry."""

from typing import Literal

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.types import ProviderConfig
from aol_llm.providers.anthropic import AnthropicProvider
from aol_llm.providers.base import Provider
from aol_llm.providers.openai_compat import OpenAICompatibleProvider

AnthropicCacheTTL = Literal["5m", "1h"]


def build_provider(
    config: ProviderConfig,
    api_key: str | None,
    prompt_cache_ttl: AnthropicCacheTTL | None = None,
) -> Provider:
    if config.kind == "anthropic":
        return AnthropicProvider(
            config=config,
            api_key=api_key,
            prompt_cache_ttl=prompt_cache_ttl,
        )
    if config.kind == "openai_compatible":
        return OpenAICompatibleProvider(config=config, api_key=api_key)
    raise UnknownProviderError(f"unknown provider kind: {config.kind}")


def build_distiller_provider(
    config: ProviderConfig,
    api_key: str | None,
    prompt_cache_ttl: AnthropicCacheTTL | None = None,
) -> Provider:
    if config.kind == "anthropic":
        return AnthropicProvider(
            config=config,
            api_key=api_key,
            prompt_cache_ttl=prompt_cache_ttl,
            adaptive_thinking=False,
        )
    return build_provider(config, api_key, prompt_cache_ttl)
