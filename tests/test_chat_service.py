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


def test_management_methods_update_conversation(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()

    renamed = service.rename_conversation(conversation.id, "Renamed")
    switched = service.switch_model(renamed.id, "anthropic", "claude-new")
    archived = service.archive_conversation(switched.id)

    assert renamed.title == "Renamed"
    assert switched.model == "claude-new"
    assert archived.archived is True
    assert service.list_conversations() == []


def test_update_system_prompt_sets_and_clears_prompt(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()

    updated = service.update_system_prompt(conversation.id, "  Be precise.  ")
    cleared = service.update_system_prompt(conversation.id, "   ")

    assert updated.system_prompt == "Be precise."
    assert cleared.system_prompt is None


def test_delete_conversation_removes_chat(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()

    service.delete_conversation(conversation.id)

    assert service.list_conversations() == []


@pytest.mark.asyncio
async def test_retry_last_response_replaces_last_assistant(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    calls: list[list[str]] = []

    class RetryProvider:
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
            del system, max_output_tokens, temperature
            calls.append([message.content for message in messages])
            yield StreamChunk(text="new", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=2, model=model),
            )

    def retry_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
    ) -> Provider:
        return RetryProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=retry_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = service.create_conversation()
    db.add_message(conversation.id, "user", "question", path=db_path)
    db.add_message(conversation.id, "assistant", "old", path=db_path)

    events = [event async for event in service.retry_last_response(conversation.id)]
    messages = db.list_messages(conversation.id, db_path)

    assert [event.text for event in events] == ["new", ""]
    assert calls == [["question"]]
    assert [message.content for message in messages] == ["question", "new"]


def test_export_conversation_writes_markdown(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()
    service.rename_conversation(conversation.id, "Export Me")
    db.add_message(conversation.id, "user", "hello", path=tmp_path / "chat.db")

    path = service.export_conversation(
        conversation.id,
        "markdown",
        directory=tmp_path / "exports",
    )

    assert path.name.startswith("export-me-")
    assert path.suffix == ".md"
    assert "### User\n\nhello" in path.read_text(encoding="utf-8")
