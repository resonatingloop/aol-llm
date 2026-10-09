"""Buddy memory distillation orchestration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import re
from typing import Literal

from aol_llm.config import AppConfig
from aol_llm.core.pricing import ModelPricing
from aol_llm.core.types import ProviderConfig
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import build_distiller_provider
from aol_llm.secrets import get_api_key

DistillMode = Literal["incremental", "refactor"]
PromptCacheTTL = Literal["5m", "1h"]
ProviderFactory = Callable[
    [ProviderConfig, str | None, PromptCacheTTL | None],
    Provider,
]
ApiKeyGetter = Callable[[str], str | None]

MAX_TRANSCRIPT_BATCH_CHARS = 80_000
MAX_OUTPUT_TOKENS = 4096
CANONICAL_HEADINGS = [
    "# claude-shaped memory",
    "## Constants",
    "### Purpose",
    "### Context",
    "### Concepts",
    "### Approach",
    "### Influences",
    "## Interpersonal",
    "### Bonds",
    "### Arcs",
    "## Threads",
    "### Projects",
    "### Tools",
]


@dataclass(frozen=True)
class DistillResult:
    buddy_id: str
    status: Literal["success", "noop"]
    batches: int
    memory_text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class InvalidMemoryOutputError(ValueError):
    """Raised when a completed distiller call returns an invalid document."""


async def distill_buddy_memory(
    buddy_id: str,
    *,
    mode: DistillMode = "incremental",
    db_path: Path | None = None,
    app_config: AppConfig | None = None,
    config_path: Path | None = None,
    provider_factory: ProviderFactory = build_distiller_provider,
    api_key_getter: ApiKeyGetter = get_api_key,
    rate_card: Mapping[str, ModelPricing] | None = None,
) -> DistillResult:
    # Hard-disabled before storage, config, secret lookup, or provider construction.
    raise ValueError("Memory is disabled; distillation is unavailable.")


def load_distiller_prompt() -> str:
    return (
        resources.files("aol_llm.data")
        .joinpath("memory_distiller_prompt.md")
        .read_text(encoding="utf-8")
    )


def validate_memory_output(current_memory: str, output: str) -> list[str]:
    errors: list[str] = []
    stripped = output.strip()
    if not stripped:
        return ["output is empty"]
    if stripped.startswith("```") or stripped.endswith("```"):
        errors.append("output is wrapped in a fenced block")
    if not (
        stripped.startswith("---") or stripped.startswith("# claude-shaped memory")
    ):
        errors.append("output has preamble before the memory document")
    headings = _headings(output)
    if headings != CANONICAL_HEADINGS:
        errors.append("output does not preserve canonical heading order")
    for descriptor in _italic_descriptor_lines(current_memory):
        if descriptor not in output:
            errors.append(f"missing descriptor line: {descriptor}")
    for comment in _html_comments(current_memory):
        if comment not in output:
            errors.append("missing canonical HTML comment")
    threads = _section_text(output, "## Threads")
    before_threads = output if threads is None else output.split("## Threads", 1)[0]
    if _non_thread_list_has_warmth_tag(before_threads):
        errors.append("warmth tag appears outside Threads")
    return errors


def _headings(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if re.fullmatch(r"#{1,3} .+", line.strip())
    ]


def _italic_descriptor_lines(text: str) -> list[str]:
    descriptors: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") and stripped.endswith("*"):
            descriptors.append(stripped)
    return descriptors


def _html_comments(text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(r"<!--.*?-->", text, re.DOTALL)]


def _section_text(text: str, heading: str) -> str | None:
    if heading not in text:
        return None
    return text.split(heading, 1)[1]


def _warmth_tag_pattern() -> re.Pattern[str]:
    return re.compile(r"\[(hot|cooling|cold)\]")


def _non_thread_list_has_warmth_tag(text: str) -> bool:
    return any(
        line.lstrip().startswith("- ") and _warmth_tag_pattern().search(line)
        for line in text.splitlines()
    )
