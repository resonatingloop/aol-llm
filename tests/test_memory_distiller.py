from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aol_llm.config import AppConfig, MemoryConfig, ProviderSettings
from aol_llm.core.errors import RateLimitError
from aol_llm.core.pricing import ModelPricing
from aol_llm.core.types import Message, ProviderConfig, StreamChunk, TokenUsage
from aol_llm.memory_distiller import (
    InvalidMemoryOutputError,
    distill_buddy_memory,
    validate_memory_output,
)
from aol_llm.providers.base import Provider
from aol_llm.storage import db


CANONICAL_MEMORY = """---
tags:
  - project
---

# claude-shaped memory

*title descriptor with [hot] tag grammar.*

<!-- keep this comment -->

## Constants

*constants descriptor.*

### Purpose
*purpose descriptor.*

### Context
*context descriptor.*

### Concepts
*concepts descriptor.*

### Approach
*approach descriptor.*

### Influences
*influences descriptor.*

## Interpersonal

*interpersonal descriptor.*

### Bonds
*bonds descriptor.*

### Arcs
*arcs descriptor.*

## Threads

*threads descriptor.*

### Projects
- old project `[hot]`

### Tools
- old tool `[cooling]`
"""

UPDATED_MEMORY = CANONICAL_MEMORY.replace(
    "- old project `[hot]`",
    "- memory distiller `[hot]` -- rewrites memory documents.",
)


class FakeProvider:
    config: ProviderConfig

    def __init__(self, outputs: list[str], *, fail: bool = False) -> None:
        self.outputs = outputs
        self.fail = fail
        self.calls: list[tuple[list[Message], str | None, str, int]] = []

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        del temperature
        self.calls.append((messages, system, model, max_output_tokens))
        if self.fail:
            raise RateLimitError("rate limited")
        output = self.outputs.pop(0)
        yield StreamChunk(text=output, done=False)
        yield StreamChunk(
            text="",
            done=True,
            usage=TokenUsage(input_tokens=10, output_tokens=20, model=model),
        )


def app_config() -> AppConfig:
    return AppConfig(
        providers={"anthropic": ProviderSettings(default_model="claude-opus-4-8")},
        memory=MemoryConfig(
            distiller_provider="anthropic",
            distiller_model="claude-opus-4-8",
        ),
    )


def test_validate_memory_output_rejects_preamble_and_missing_structure() -> None:
    errors = validate_memory_output(CANONICAL_MEMORY, "Here is the update.\n\nnope")

    assert "output has preamble before the memory document" in errors
    assert "output does not preserve canonical heading order" in errors


def test_validate_memory_output_accepts_canonical_shape() -> None:
    assert validate_memory_output(CANONICAL_MEMORY, UPDATED_MEMORY) == []


@pytest.mark.asyncio
async def test_distill_noops_without_provider_call_when_no_new_messages(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-opus-4-8", db_path)
    provider = FakeProvider([UPDATED_MEMORY])

    def provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del config, api_key, prompt_cache_ttl
        return provider

    result = await distill_buddy_memory(
        buddy.id,
        db_path=db_path,
        app_config=app_config(),
        provider_factory=provider_factory,
        api_key_getter=lambda provider_id: "secret",
    )

    assert result.status == "noop"
    assert provider.calls == []
    assert db.list_memory_distill_runs(buddy.id, db_path)[0].status == "noop"


@pytest.mark.asyncio
async def test_distill_commits_valid_output_and_advances_watermark(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-opus-4-8", db_path)
    db.upsert_buddy_memory(buddy.id, CANONICAL_MEMORY, path=db_path)
    conversation = db.create_conversation(
        "Chat",
        "anthropic",
        "claude-opus-4-8",
        buddy_id=buddy.id,
        path=db_path,
    )
    message = db.add_message(conversation.id, "user", "distill this", path=db_path)
    provider = FakeProvider([UPDATED_MEMORY])

    def provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del api_key, prompt_cache_ttl
        assert config.default_model == "claude-opus-4-8"
        return provider

    result = await distill_buddy_memory(
        buddy.id,
        mode="refactor",
        db_path=db_path,
        app_config=app_config(),
        provider_factory=provider_factory,
        api_key_getter=lambda provider_id: "secret",
        rate_card={
            "claude-opus-4-8": ModelPricing(
                input_per_mtok=1.0,
                output_per_mtok=2.0,
            )
        },
    )
    memory = db.get_buddy_memory(buddy.id, db_path)
    runs = db.list_memory_distill_runs(buddy.id, db_path)

    assert result.status == "success"
    assert result.batches == 1
    assert result.cost_usd == 0.00005
    assert memory is not None
    assert memory.memory_text == UPDATED_MEMORY
    assert memory.watermark_message_id == message.id
    assert runs[0].status == "success"
    assert runs[0].mode == "refactor"
    assert provider.calls[0][0][0].content.endswith("<mode>\nrefactor\n</mode>")


@pytest.mark.asyncio
async def test_distill_rejects_invalid_output_without_advancing_watermark(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-opus-4-8", db_path)
    db.upsert_buddy_memory(buddy.id, CANONICAL_MEMORY, path=db_path)
    conversation = db.create_conversation(
        "Chat",
        "anthropic",
        "claude-opus-4-8",
        buddy_id=buddy.id,
        path=db_path,
    )
    db.add_message(conversation.id, "user", "distill this", path=db_path)
    provider = FakeProvider(["garbage"])

    def provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del config, api_key, prompt_cache_ttl
        return provider

    with pytest.raises(InvalidMemoryOutputError):
        await distill_buddy_memory(
            buddy.id,
            db_path=db_path,
            app_config=app_config(),
            provider_factory=provider_factory,
            api_key_getter=lambda provider_id: "secret",
        )

    memory = db.get_buddy_memory(buddy.id, db_path)
    runs = db.list_memory_distill_runs(buddy.id, db_path)

    assert memory is not None
    assert memory.memory_text == CANONICAL_MEMORY
    assert memory.watermark_message_id is None
    assert runs[0].status == "failed"
    assert runs[0].failure_reason is not None
    assert runs[0].failure_reason.startswith("invalid_output:")


@pytest.mark.asyncio
async def test_distill_records_provider_failure_without_updating_memory(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-opus-4-8", db_path)
    db.upsert_buddy_memory(buddy.id, CANONICAL_MEMORY, path=db_path)
    conversation = db.create_conversation(
        "Chat",
        "anthropic",
        "claude-opus-4-8",
        buddy_id=buddy.id,
        path=db_path,
    )
    db.add_message(conversation.id, "user", "distill this", path=db_path)
    provider = FakeProvider([], fail=True)

    def provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del config, api_key, prompt_cache_ttl
        return provider

    with pytest.raises(RateLimitError):
        await distill_buddy_memory(
            buddy.id,
            db_path=db_path,
            app_config=app_config(),
            provider_factory=provider_factory,
            api_key_getter=lambda provider_id: "secret",
        )

    memory = db.get_buddy_memory(buddy.id, db_path)
    runs = db.list_memory_distill_runs(buddy.id, db_path)

    assert memory is not None
    assert memory.memory_text == CANONICAL_MEMORY
    assert memory.watermark_message_id is None
    assert runs[0].status == "failed"
    assert runs[0].failure_reason == "RateLimitError"


@pytest.mark.asyncio
async def test_distill_batches_oldest_first_with_same_codepath(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("aol_llm.memory_distiller.MAX_TRANSCRIPT_BATCH_CHARS", 5)
    db_path = tmp_path / "chat.db"
    db.init_db(db_path)
    buddy = db.ensure_buddy("anthropic", "claude-opus-4-8", db_path)
    db.upsert_buddy_memory(buddy.id, CANONICAL_MEMORY, path=db_path)
    conversation = db.create_conversation(
        "Chat",
        "anthropic",
        "claude-opus-4-8",
        buddy_id=buddy.id,
        path=db_path,
    )
    first = db.add_message(conversation.id, "user", "first message", path=db_path)
    second = db.add_message(
        conversation.id, "assistant", "second message", path=db_path
    )
    provider = FakeProvider([UPDATED_MEMORY, UPDATED_MEMORY])

    def provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del config, api_key, prompt_cache_ttl
        return provider

    result = await distill_buddy_memory(
        buddy.id,
        db_path=db_path,
        app_config=app_config(),
        provider_factory=provider_factory,
        api_key_getter=lambda provider_id: "secret",
    )
    runs = db.list_memory_distill_runs(buddy.id, db_path)

    assert result.batches == 2
    assert len(provider.calls) == 2
    assert first.id in provider.calls[0][0][0].content
    assert second.id in provider.calls[1][0][0].content
    assert [run.watermark_message_id for run in runs] == [first.id, second.id]
