from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aol_llm.chat import ChatService
from aol_llm.config import default_config
from aol_llm.core.types import Message, ProviderConfig, StreamChunk, TokenUsage
from aol_llm.memory_distiller import distill_buddy_memory
from aol_llm.prompt_assembly import assemble_prompt, should_inject_memory
from aol_llm.storage import db


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["incremental", "refactor"])
async def test_distillation_refuses_before_any_key_or_provider_lookup(
    tmp_path: Path, mode: str
) -> None:
    from typing import cast

    from aol_llm.memory_distiller import DistillMode

    def forbidden(*args: object) -> None:
        pytest.fail("disabled memory accessed a provider or API key")

    with pytest.raises(ValueError, match="Memory is disabled"):
        await distill_buddy_memory(
            "not-even-a-real-buddy",
            mode=cast(DistillMode, mode),
            db_path=tmp_path / "must-not-create.db",
            api_key_getter=forbidden,
            provider_factory=forbidden,  # type: ignore[arg-type]
        )
    assert not (tmp_path / "must-not-create.db").exists()


def test_enabled_saved_memory_is_never_injected(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    db.init_db(path)
    buddy = db.ensure_buddy("anthropic", "claude-test", path)
    memory = db.upsert_buddy_memory(buddy.id, "Must not reach a model", path=path)
    assert memory.enabled
    assert should_inject_memory(memory) is False
    assert assemble_prompt("Ordinary prompt", memory).system_text == "Ordinary prompt"
    assert assemble_prompt(None, memory).system_text is None
    assert db.get_buddy_memory(buddy.id, path) == memory


def test_memory_cannot_be_reenabled_on_restart_or_buddy_switch(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    service = ChatService(db_path=path, app_config=default_config())
    service.init()
    buddies = service.list_buddies()
    for buddy in buddies:
        db.upsert_buddy_memory(buddy.id, "Old memory", path=path, enabled=True)
    reloaded = ChatService(db_path=path, app_config=default_config())
    reloaded.init()
    for buddy in reversed(buddies):
        assert reloaded.buddy_memory_status(buddy.id).label == "memory disabled"
        assert reloaded.should_auto_distill_buddy(buddy.id) is False
        with pytest.raises(ValueError, match="Memory is disabled"):
            reloaded.set_buddy_memory_enabled(buddy.id, True)
        assert reloaded.buddy_memory_status(buddy.id).label == "memory disabled"
        assert db.get_buddy_memory(buddy.id, path) is not None


@pytest.mark.asyncio
async def test_chat_send_and_retry_ignore_saved_memory(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    systems: list[str | None] = []

    class ChatProvider:
        config: ProviderConfig

        def __init__(self, config: ProviderConfig) -> None:
            self.config = config

        async def stream(
            self,
            messages: list[Message],
            system: str | None,
            model: str,
            max_output_tokens: int = 4096,
            temperature: float = 1.0,
        ) -> AsyncIterator[StreamChunk]:
            systems.append(system)
            yield StreamChunk(text="reply", done=False)
            yield StreamChunk(text="", done=True, usage=TokenUsage(1, 1, model))

    def factory(
        config: ProviderConfig,
        api_key: str | None,
        ttl: str | None = None,
    ) -> ChatProvider:
        return ChatProvider(config)

    service = ChatService(
        db_path=path,
        app_config=default_config(),
        provider_factory=factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = service.create_conversation()
    service.update_system_prompt(conversation.id, "Ordinary prompt")
    assert conversation.buddy_id is not None
    before = db.upsert_buddy_memory(conversation.buddy_id, "Secret memory", path=path)
    _ = [event async for event in service.send_message(conversation.id, "hello")]
    _ = [event async for event in service.retry_last_response(conversation.id)]
    assert systems == ["Ordinary prompt", "Ordinary prompt"]
    assert db.get_buddy_memory(conversation.buddy_id, path) == before
    assert db.list_memory_distill_runs(conversation.buddy_id, path) == []
