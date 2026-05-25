"""Canonical provider-neutral data types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Role = Literal["user", "assistant"]
ProviderKind = Literal["anthropic", "openai_compatible"]


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    role: Role
    content: str
    created_at: datetime
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    system_prompt: str | None
    provider_id: str
    model: str
    created_at: datetime
    updated_at: datetime
    archived: bool = False


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: ProviderKind
    display_name: str
    base_url: str | None
    keyring_service: str | None
    default_model: str
    available_models: list[str]


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    model: str


@dataclass(frozen=True)
class StreamChunk:
    text: str
    done: bool
    usage: TokenUsage | None = None
