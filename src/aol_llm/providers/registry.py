"""Provider adapter registry."""

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.types import ProviderConfig
from aol_llm.providers.anthropic import AnthropicProvider
from aol_llm.providers.base import Provider
from aol_llm.providers.openai_compat import OpenAICompatibleProvider


def build_provider(config: ProviderConfig, api_key: str | None) -> Provider:
    if config.kind == "anthropic":
        return AnthropicProvider(config=config, api_key=api_key)
    if config.kind == "openai_compatible":
        return OpenAICompatibleProvider(config=config, api_key=api_key)
    raise UnknownProviderError(f"unknown provider kind: {config.kind}")
