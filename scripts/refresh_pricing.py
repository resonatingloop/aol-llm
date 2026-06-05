"""Refresh the vendored pricing snapshot from LiteLLM."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.request import urlopen

from aol_llm.chat import DEFAULT_PROVIDER_MODELS
from aol_llm.config import default_config

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
SNAPSHOT_PATH = Path("src/aol_llm/data/model_prices.json")
PROVIDER_PREFIX_FALLBACKS = {
    "mistral": ("mistral/{model}",),
    "xai": ("xai/{model}",),
}


def main() -> None:
    upstream = _download_upstream()
    snapshot = {
        "source_url": UPSTREAM_URL,
        "models": {
            model: _snapshot_entry(provider_id, model, upstream)
            for provider_id, model in _built_in_models()
        },
    }
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _download_upstream() -> Mapping[str, object]:
    with urlopen(UPSTREAM_URL, timeout=30) as response:
        raw = json.loads(response.read().decode("utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("LiteLLM pricing data must be a JSON object")
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _built_in_models() -> list[tuple[str, str]]:
    models: set[tuple[str, str]] = set()
    for provider_id, settings in default_config().providers.items():
        models.add((provider_id, settings.default_model))
        for model in DEFAULT_PROVIDER_MODELS.get(provider_id, ()):
            models.add((provider_id, model))
    return sorted(models)


def _snapshot_entry(
    provider_id: str,
    model: str,
    upstream: Mapping[str, object],
) -> dict[str, object]:
    upstream_model = _upstream_model_key(provider_id, model, upstream)
    if upstream_model is None:
        return {
            "priced": False,
            "reason": "missing_from_litellm_snapshot",
            "upstream_model": None,
        }

    upstream_entry = upstream[upstream_model]
    if not isinstance(upstream_entry, Mapping):
        return {
            "priced": False,
            "reason": "invalid_litellm_entry",
            "upstream_model": upstream_model,
        }

    input_cost = upstream_entry.get("input_cost_per_token")
    output_cost = upstream_entry.get("output_cost_per_token")
    if not _is_number(input_cost) or not _is_number(output_cost):
        return {
            "priced": False,
            "reason": "missing_litellm_rates",
            "upstream_model": upstream_model,
        }

    return {
        "priced": True,
        "input_per_mtok": float(input_cost) * 1_000_000,
        "output_per_mtok": float(output_cost) * 1_000_000,
        "upstream_model": upstream_model,
    }


def _upstream_model_key(
    provider_id: str,
    model: str,
    upstream: Mapping[str, object],
) -> str | None:
    if model in upstream:
        return model
    for template in PROVIDER_PREFIX_FALLBACKS.get(provider_id, ()):
        candidate = template.format(model=model)
        if candidate in upstream:
            return candidate
    return None


def _is_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float)


if __name__ == "__main__":
    main()
