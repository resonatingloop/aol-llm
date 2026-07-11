"""Canonical provider-neutral data types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Role = Literal["user", "assistant"]
ProviderKind = Literal["anthropic", "openai_compatible"]
PromptStatus = Literal["draft", "canonical", "archived"]


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
    prompt_version_id: str | None = None
    cache_creation_5m_input_tokens: int | None = None
    cache_creation_1h_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    system_prompt: str | None
    provider_id: str
    model: str
    created_at: datetime
    updated_at: datetime
    buddy_id: str | None = None
    prompt_version_id: str | None = None
    assistant_name: str | None = None
    archived: bool = False


@dataclass(frozen=True)
class Buddy:
    id: str
    name: str
    screen_name: str
    provider_id: str
    model: str
    prompt_id: str | None
    prompt_version_id: str | None
    created_at: datetime
    updated_at: datetime
    archived: bool = False


@dataclass(frozen=True)
class BuddyMemory:
    buddy_id: str
    memory_text: str
    enabled: bool
    suppress_injection: bool
    watermark_created_at: str | None
    watermark_message_id: str | None
    updated_at: datetime


@dataclass(frozen=True)
class Prompt:
    id: str
    name: str
    gloss: str
    core: str
    signature: str | None
    default_provider: str | None
    default_model: str | None
    status: PromptStatus
    doorwords: str | None
    horizon_minutes: int | None
    mischief_range: str | None
    dismissal_protocol: str | None
    ritual_twin_id: str | None
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PromptVersion:
    id: str
    prompt_id: str
    parent_version_id: str | None
    name: str
    gloss: str
    core: str
    signature: str | None
    default_provider: str | None
    default_model: str | None
    status: PromptStatus
    doorwords: str | None
    horizon_minutes: int | None
    mischief_range: str | None
    dismissal_protocol: str | None
    ritual_twin_id: str | None
    note: str | None
    created_at: datetime


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
    cache_creation_5m_input_tokens: int | None = None
    cache_creation_1h_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResponseMetadata:
    model: str | None
    response_id: str | None


@dataclass(frozen=True)
class StreamChunk:
    text: str
    done: bool
    usage: TokenUsage | None = None
    response_metadata: ProviderResponseMetadata | None = None
