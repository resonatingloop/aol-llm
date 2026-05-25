from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aol_llm.chat import ChatService
from aol_llm.config import AppConfig, ProviderSettings, UIConfig
from aol_llm.core.pricing import ModelPricing
from aol_llm.core.types import Message, ProviderConfig, StreamChunk, TokenUsage
from aol_llm.providers.base import Provider
from aol_llm.storage import db


class FakeProvider:
    config: ProviderConfig

    def __init__(self, config: ProviderConfig, api_key: str | None) -> None:
        self.config = config
        self.api_key = api_key

    async def stream(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncIterator[StreamChunk]:
        del max_output_tokens, temperature
        assert self.api_key == "secret"
        assert system == "Be concise."
        assert [message.role for message in messages] == ["user"]
        assert messages[0].content == "hello"
        yield StreamChunk(text="he", done=False)
        yield StreamChunk(text="llo", done=False)
        yield StreamChunk(
            text="",
            done=True,
            usage=TokenUsage(input_tokens=10, output_tokens=20, model=model),
        )


def app_config() -> AppConfig:
    return AppConfig(
        ui=UIConfig(default_provider="anthropic"),
        providers={"anthropic": ProviderSettings(default_model="claude-test")},
    )


def provider_factory(config: ProviderConfig, api_key: str | None) -> Provider:
    return FakeProvider(config, api_key)


@pytest.mark.asyncio
async def test_send_message_streams_and_persists_messages(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=provider_factory,
        api_key_getter=lambda provider_id: "secret",
        rate_card={
            "claude-test": ModelPricing(input_per_mtok=1.0, output_per_mtok=2.0)
        },
    )
    service.init()
    conversation = service.create_conversation()
    conversation = db.update_conversation(
        conversation.id,
        path=db_path,
        system_prompt="Be concise.",
    )

    events = [event async for event in service.send_message(conversation.id, "hello")]
    messages = db.list_messages(conversation.id, db_path)

    assert [event.text for event in events] == ["he", "llo", ""]
    assert events[-1].done is True
    assert events[-1].input_tokens == 10
    assert events[-1].output_tokens == 20
    assert events[-1].cost_usd == 0.00005
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "hello"
    assert messages[1].content == "hello"
    assert messages[1].input_tokens == 10
    assert messages[1].output_tokens == 20
    assert messages[1].cost_usd == 0.00005


def test_ensure_conversation_creates_default_when_empty(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()

    conversation = service.ensure_conversation()

    assert conversation.title == "New chat"
    assert conversation.provider_id == "anthropic"
    assert conversation.model == "claude-test"
