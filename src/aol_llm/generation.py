"""Stateless provider generation facade for non-UI consumers."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd, load_rate_card
from aol_llm.core.requests import NormalizedChatRequest
from aol_llm.core.types import ProviderConfig, ProviderKind, TokenUsage
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import AnthropicCacheTTL, build_provider

ProviderFactory = Callable[
    [ProviderConfig, str | None, AnthropicCacheTTL | None], Provider
]


@dataclass(frozen=True)
class GenerationResult:
    text: str
    usage: TokenUsage
    cost_usd: float | None
    provider_id: str
    provider_kind: ProviderKind
    requested_model: str
    reported_model: str | None
    provider_response_id: str | None
    termination_reason: str | None = None
    service_tier: str | None = None


async def generate(
    provider_config: ProviderConfig,
    api_key: str | None,
    request: NormalizedChatRequest,
    *,
    prompt_cache_ttl: AnthropicCacheTTL | None = None,
    rate_card: Mapping[str, ModelPricing] | None = None,
    provider_factory: ProviderFactory = build_provider,
) -> GenerationResult:
    """Collect one provider stream without persistence, retries, or UI behavior."""

    provider = provider_factory(provider_config, api_key, prompt_cache_ttl)
    pricing = load_rate_card() if rate_card is None else rate_card
    parts: list[str] = []

    async for chunk in provider.stream(
        messages=list(request.messages),
        system=request.system,
        model=request.model,
        max_output_tokens=request.max_output_tokens,
        temperature=request.temperature,
    ):
        if chunk.text:
            parts.append(chunk.text)
        if not chunk.done:
            if chunk.usage is not None or chunk.response_metadata is not None:
                raise UnknownProviderError(
                    "provider returned final metadata on a non-final chunk"
                )
            continue
        if chunk.usage is None:
            raise UnknownProviderError("provider final chunk was missing usage")

        metadata = chunk.response_metadata
        return GenerationResult(
            text="".join(parts),
            usage=chunk.usage,
            cost_usd=estimate_cost_usd(chunk.usage, pricing),
            provider_id=provider_config.id,
            provider_kind=provider_config.kind,
            requested_model=request.model,
            reported_model=None if metadata is None else metadata.model,
            provider_response_id=None if metadata is None else metadata.response_id,
            termination_reason=(
                None if metadata is None else metadata.termination_reason
            ),
            service_tier=None if metadata is None else metadata.service_tier,
        )

    raise UnknownProviderError("provider stream ended without a final chunk")
