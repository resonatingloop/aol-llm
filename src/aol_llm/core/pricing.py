"""Token usage cost calculations."""

from dataclasses import dataclass
from typing import Mapping

from aol_llm.core.types import TokenUsage


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: float
    output_per_mtok: float


def estimate_cost_usd(
    usage: TokenUsage,
    rate_card: Mapping[str, ModelPricing],
) -> float | None:
    """Estimate USD cost from token usage and per-million-token rates."""

    pricing = rate_card.get(usage.model)
    if pricing is None:
        return None

    input_cost = usage.input_tokens * pricing.input_per_mtok / 1_000_000
    output_cost = usage.output_tokens * pricing.output_per_mtok / 1_000_000
    return input_cost + output_cost
