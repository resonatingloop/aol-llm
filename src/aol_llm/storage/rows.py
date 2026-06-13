"""SQLite row conversion helpers."""

from datetime import datetime
import json
import sqlite3
from typing import Literal, cast

from aol_llm.core.types import (
    Buddy,
    BuddyMemory,
    Conversation,
    Message,
    Prompt,
    PromptStatus,
    PromptVersion,
    ProviderConfig,
)


def format_dt(value: datetime) -> str:
    return value.isoformat()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def db_value(value: object) -> object:
    if isinstance(value, bool):
        return int(value)
    return value


def conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=cast(str, row["id"]),
        title=cast(str, row["title"]),
        system_prompt=cast(str | None, row["system_prompt"]),
        provider_id=cast(str, row["provider_id"]),
        model=cast(str, row["model"]),
        created_at=parse_dt(cast(str, row["created_at"])),
        updated_at=parse_dt(cast(str, row["updated_at"])),
        buddy_id=cast(str | None, row["buddy_id"]),
        prompt_version_id=cast(str | None, row["prompt_version_id"]),
        assistant_name=cast(str | None, row["assistant_name"]),
        archived=bool(row["archived"]),
    )


def message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        id=cast(str, row["id"]),
        conversation_id=cast(str, row["conversation_id"]),
        role=cast(Literal["user", "assistant"], row["role"]),
        content=cast(str, row["content"]),
        created_at=parse_dt(cast(str, row["created_at"])),
        model=cast(str | None, row["model"]),
        input_tokens=cast(int | None, row["input_tokens"]),
        output_tokens=cast(int | None, row["output_tokens"]),
        cost_usd=cast(float | None, row["cost_usd"]),
        prompt_version_id=cast(str | None, row["prompt_version_id"]),
        cache_creation_5m_input_tokens=cast(
            int | None,
            row["cache_creation_5m_input_tokens"],
        ),
        cache_creation_1h_input_tokens=cast(
            int | None,
            row["cache_creation_1h_input_tokens"],
        ),
        cache_read_input_tokens=cast(int | None, row["cache_read_input_tokens"]),
    )


def buddy_from_row(row: sqlite3.Row) -> Buddy:
    return Buddy(
        id=cast(str, row["id"]),
        name=cast(str, row["name"]),
        screen_name=cast(str, row["screen_name"]),
        provider_id=cast(str, row["provider_id"]),
        model=cast(str, row["model"]),
        prompt_id=cast(str | None, row["prompt_id"]),
        prompt_version_id=cast(str | None, row["prompt_version_id"]),
        created_at=parse_dt(cast(str, row["created_at"])),
        updated_at=parse_dt(cast(str, row["updated_at"])),
        archived=bool(row["archived"]),
    )


def buddy_memory_from_row(row: sqlite3.Row) -> BuddyMemory:
    return BuddyMemory(
        buddy_id=cast(str, row["buddy_id"]),
        memory_text=cast(str, row["memory_text"]),
        enabled=bool(row["enabled"]),
        suppress_injection=bool(row["suppress_injection"]),
        watermark_created_at=cast(str | None, row["watermark_created_at"]),
        watermark_message_id=cast(str | None, row["watermark_message_id"]),
        updated_at=parse_dt(cast(str, row["updated_at"])),
    )


def prompt_from_row(row: sqlite3.Row) -> Prompt:
    return Prompt(
        id=cast(str, row["id"]),
        name=cast(str, row["name"]),
        gloss=cast(str, row["gloss"]),
        core=cast(str, row["core"]),
        signature=cast(str | None, row["signature"]),
        default_provider=cast(str | None, row["default_provider"]),
        default_model=cast(str | None, row["default_model"]),
        status=cast(PromptStatus, row["status"]),
        doorwords=cast(str | None, row["doorwords"]),
        horizon_minutes=cast(int | None, row["horizon_minutes"]),
        mischief_range=cast(str | None, row["mischief_range"]),
        dismissal_protocol=cast(str | None, row["dismissal_protocol"]),
        ritual_twin_id=cast(str | None, row["ritual_twin_id"]),
        current_version_id=cast(str | None, row["current_version_id"]),
        created_at=parse_dt(cast(str, row["created_at"])),
        updated_at=parse_dt(cast(str, row["updated_at"])),
    )


def prompt_version_from_row(row: sqlite3.Row) -> PromptVersion:
    return PromptVersion(
        id=cast(str, row["id"]),
        prompt_id=cast(str, row["prompt_id"]),
        parent_version_id=cast(str | None, row["parent_version_id"]),
        name=cast(str, row["name"]),
        gloss=cast(str, row["gloss"]),
        core=cast(str, row["core"]),
        signature=cast(str | None, row["signature"]),
        default_provider=cast(str | None, row["default_provider"]),
        default_model=cast(str | None, row["default_model"]),
        status=cast(PromptStatus, row["status"]),
        doorwords=cast(str | None, row["doorwords"]),
        horizon_minutes=cast(int | None, row["horizon_minutes"]),
        mischief_range=cast(str | None, row["mischief_range"]),
        dismissal_protocol=cast(str | None, row["dismissal_protocol"]),
        ritual_twin_id=cast(str | None, row["ritual_twin_id"]),
        note=cast(str | None, row["note"]),
        created_at=parse_dt(cast(str, row["created_at"])),
    )


def provider_from_row(row: sqlite3.Row) -> ProviderConfig:
    models = json.loads(cast(str, row["available_models_json"]))
    if not isinstance(models, list) or not all(
        isinstance(model, str) for model in models
    ):
        raise ValueError("provider available_models_json must be a JSON string array")
    return ProviderConfig(
        id=cast(str, row["id"]),
        kind=cast(Literal["anthropic", "openai_compatible"], row["kind"]),
        display_name=cast(str, row["display_name"]),
        base_url=cast(str | None, row["base_url"]),
        keyring_service=cast(str | None, row["keyring_service"]),
        default_model=cast(str, row["default_model"]),
        available_models=cast(list[str], models),
    )
