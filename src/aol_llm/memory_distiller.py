"""Buddy memory distillation orchestration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from aol_llm.config import AppConfig, load_config
from aol_llm.core.errors import ProviderError, UnknownProviderError
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd, load_rate_card
from aol_llm.core.types import Message, ProviderConfig, ProviderKind, TokenUsage
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import build_distiller_provider
from aol_llm.secrets import get_api_key
from aol_llm.storage import db
from aol_llm.storage.rows import format_dt

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
    db.init_db(db_path)
    config = app_config or load_config(config_path)
    provider_id = config.memory.distiller_provider
    model = config.memory.distiller_model
    provider_config = _provider_config(config, provider_id, model)
    provider = provider_factory(
        provider_config,
        api_key_getter(provider_id),
        None,
    )
    pricing = load_rate_card() if rate_card is None else rate_card
    memory = db.get_buddy_memory(buddy_id, db_path)
    current_memory = "" if memory is None else memory.memory_text
    pending = db.messages_newer_than_watermark_for_buddy(buddy_id, db_path)
    if not pending:
        db.record_memory_distill_run(
            buddy_id=buddy_id,
            provider_id=provider_id,
            model=model,
            mode=mode,
            status="noop",
            path=db_path,
        )
        return DistillResult(
            buddy_id=buddy_id,
            status="noop",
            batches=0,
            memory_text=current_memory,
        )

    prompt = load_distiller_prompt()
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost: float | None = 0.0
    batches = 0

    while pending:
        batch, pending = _split_next_batch(pending)
        try:
            rewritten, usage = await _run_distiller_batch(
                provider=provider,
                prompt=prompt,
                current_memory=current_memory,
                transcript_slice=_format_transcript_slice(batch),
                mode=mode,
                model=model,
            )
        except ProviderError as error:
            db.record_memory_distill_run(
                buddy_id=buddy_id,
                provider_id=provider_id,
                model=model,
                mode=mode,
                status="failed",
                path=db_path,
                failure_reason=error.__class__.__name__,
            )
            raise

        cost_usd = estimate_cost_usd(usage, pricing)
        errors = validate_memory_output(current_memory, rewritten)
        if errors:
            db.record_memory_distill_run(
                buddy_id=buddy_id,
                provider_id=provider_id,
                model=model,
                mode=mode,
                status="failed",
                path=db_path,
                usage=usage,
                cost_usd=cost_usd,
                failure_reason=f"invalid_output: {'; '.join(errors)}",
            )
            raise InvalidMemoryOutputError("; ".join(errors))

        db.commit_buddy_memory_distill(
            buddy_id=buddy_id,
            memory_text=rewritten,
            watermark_message=batch[-1],
            provider_id=provider_id,
            mode=mode,
            usage=usage,
            cost_usd=cost_usd,
            path=db_path,
        )
        current_memory = rewritten
        total_input_tokens += usage.input_tokens
        total_output_tokens += usage.output_tokens
        total_cost = _add_cost(total_cost, cost_usd)
        batches += 1

    return DistillResult(
        buddy_id=buddy_id,
        status="success",
        batches=batches,
        memory_text=current_memory,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=total_cost,
    )


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


async def _run_distiller_batch(
    *,
    provider: Provider,
    prompt: str,
    current_memory: str,
    transcript_slice: str,
    mode: DistillMode,
    model: str,
) -> tuple[str, TokenUsage]:
    text = ""
    usage = None
    async for chunk in provider.stream(
        messages=[
            _distiller_request_message(
                current_memory=current_memory,
                transcript_slice=transcript_slice,
                mode=mode,
            )
        ],
        system=prompt,
        model=model,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    ):
        if not chunk.done:
            text += chunk.text
            continue
        usage = chunk.usage
    if usage is None:
        raise UnknownProviderError("distiller stream ended without usage")
    return text, usage


def _distiller_request_message(
    *,
    current_memory: str,
    transcript_slice: str,
    mode: DistillMode,
) -> Message:
    content = "\n".join(
        [
            "<current_memory>",
            _escape_runtime_text(current_memory),
            "</current_memory>",
            "",
            "<transcript_slice>",
            _escape_runtime_text(transcript_slice),
            "</transcript_slice>",
            "",
            "<mode>",
            mode,
            "</mode>",
        ]
    )
    return Message(
        id=uuid4().hex,
        conversation_id="memory-distiller",
        role="user",
        content=content,
        created_at=datetime.now(UTC),
    )


def _format_transcript_slice(messages: list[Message]) -> str:
    blocks = []
    for message in messages:
        blocks.append(
            "\n".join(
                [
                    f"message_id: {message.id}",
                    f"conversation_id: {message.conversation_id}",
                    f"created_at: {format_dt(message.created_at)}",
                    f"role: {message.role}",
                    "content:",
                    message.content,
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _split_next_batch(messages: list[Message]) -> tuple[list[Message], list[Message]]:
    batch: list[Message] = []
    batch_chars = 0
    for index, message in enumerate(messages):
        message_chars = len(message.content)
        if batch and batch_chars + message_chars > MAX_TRANSCRIPT_BATCH_CHARS:
            return batch, messages[index:]
        batch.append(message)
        batch_chars += message_chars
    return batch, []


def _provider_config(config: AppConfig, provider_id: str, model: str) -> ProviderConfig:
    settings = config.providers[provider_id]
    kind: ProviderKind = (
        "anthropic" if provider_id == "anthropic" else "openai_compatible"
    )
    models = [model]
    if settings.default_model not in models:
        models.append(settings.default_model)
    return ProviderConfig(
        id=provider_id,
        kind=kind,
        display_name=provider_id,
        base_url=settings.base_url,
        keyring_service=f"aol-llm.{provider_id}",
        default_model=model,
        available_models=models,
    )


def _escape_runtime_text(text: str) -> str:
    return text.replace("</", "<\\/")


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


def _add_cost(total: float | None, cost: float | None) -> float | None:
    if total is None or cost is None:
        return None
    return total + cost
