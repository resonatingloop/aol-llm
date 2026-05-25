"""SQLite row conversion helpers."""

from datetime import datetime
import json
import sqlite3
from typing import Literal, cast

from aol_llm.core.types import Conversation, Message, ProviderConfig


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
