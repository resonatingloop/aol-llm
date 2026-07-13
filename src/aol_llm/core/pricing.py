"""Token usage cost calculations."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from importlib.resources import files
from pathlib import Path

from aol_llm.core.types import TokenUsage


PRICING_SNAPSHOT_PACKAGE = "aol_llm.data"
PRICING_SNAPSHOT_FILE = "model_prices.json"


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: float
    output_per_mtok: float


def load_pricing_snapshot(path: Path | None = None) -> dict[str, dict[str, object]]:
    """Load the vendored pricing snapshot model entries."""

    data = _load_snapshot_data(path)
    models = _mapping_value(data.get("models"), "models")
    return {
        model: dict(_mapping_value(entry, f"models.{model}"))
        for model, entry in models.items()
    }


def load_rate_card(path: Path | None = None) -> dict[str, ModelPricing]:
    """Load priced models from the vendored pricing snapshot."""

    rate_card: dict[str, ModelPricing] = {}
    for model, entry in load_pricing_snapshot(path).items():
        if entry.get("priced") is not True:
            continue
        rate_card[model] = ModelPricing(
            input_per_mtok=_float_value(entry, "input_per_mtok", model),
            output_per_mtok=_float_value(entry, "output_per_mtok", model),
        )
    return rate_card


def estimate_cost_usd(
    usage: TokenUsage,
    rate_card: Mapping[str, ModelPricing],
) -> float | None:
    """Estimate USD cost from token usage and per-million-token rates."""

    pricing = rate_card.get(usage.model)
    if pricing is None:
        return None
    if usage.cache_write_input_tokens is not None and (
        usage.cache_creation_5m_input_tokens is not None
        or usage.cache_creation_1h_input_tokens is not None
    ):
        raise ValueError(
            "generic and Anthropic cache-write token fields are mutually exclusive"
        )

    input_cost = usage.input_tokens * pricing.input_per_mtok / 1_000_000
    cache_creation_5m_cost = (
        (usage.cache_creation_5m_input_tokens or 0)
        * pricing.input_per_mtok
        * 1.25
        / 1_000_000
    )
    cache_creation_1h_cost = (
        (usage.cache_creation_1h_input_tokens or 0)
        * pricing.input_per_mtok
        * 2.0
        / 1_000_000
    )
    cache_read_cost = (
        (usage.cache_read_input_tokens or 0) * pricing.input_per_mtok * 0.1 / 1_000_000
    )
    cache_write_cost = (
        (usage.cache_write_input_tokens or 0)
        * pricing.input_per_mtok
        * 1.25
        / 1_000_000
    )
    output_cost = usage.output_tokens * pricing.output_per_mtok / 1_000_000
    return (
        input_cost
        + cache_creation_5m_cost
        + cache_creation_1h_cost
        + cache_read_cost
        + cache_write_cost
        + output_cost
    )


def _load_snapshot_data(path: Path | None) -> dict[str, object]:
    if path is None:
        text = (
            files(PRICING_SNAPSHOT_PACKAGE)
            .joinpath(PRICING_SNAPSHOT_FILE)
            .read_text(encoding="utf-8")
        )
    else:
        text = path.read_text(encoding="utf-8")

    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("pricing snapshot must be a JSON object")
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _mapping_value(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"pricing snapshot field must be an object: {name}")
    return {key: child for key, child in value.items() if isinstance(key, str)}


def _float_value(entry: Mapping[str, object], key: str, model: str) -> float:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"priced model {model} missing numeric {key}")
    return float(value)
