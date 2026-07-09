from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aol_llm.chat import ChatService
from aol_llm.config import AppConfig, ProviderSettings, UIConfig, default_config
from aol_llm.core.pricing import ModelPricing
from aol_llm.core.types import (
    Message,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)
from aol_llm.memory_distiller import DistillResult
from aol_llm.prompt_assembly import MEMORY_BLOCK_HEADING
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
            usage=TokenUsage(
                input_tokens=10,
                output_tokens=20,
                model=model,
                cache_creation_5m_input_tokens=0,
                cache_creation_1h_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def app_config() -> AppConfig:
    return AppConfig(
        ui=UIConfig(default_provider="anthropic"),
        providers={"anthropic": ProviderSettings(default_model="claude-test")},
    )


def provider_factory(
    config: ProviderConfig,
    api_key: str | None,
    prompt_cache_ttl: str | None = None,
) -> Provider:
    del prompt_cache_ttl
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
    conversation = service.update_system_prompt(conversation.id, "Be concise.")

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
    assert messages[1].cache_creation_5m_input_tokens == 0
    assert messages[1].cache_creation_1h_input_tokens == 0
    assert messages[1].cache_read_input_tokens == 0
    assert (
        messages[1].prompt_version_id
        == db.get_conversation(
            conversation.id,
            db_path,
        ).prompt_version_id
    )


@pytest.mark.asyncio
async def test_openai_compatible_send_persists_unreported_cache_fields_as_null(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"

    class OpenAIProvider:
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
            del messages, system, max_output_tokens, temperature
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=2, model=model),
            )

    def openai_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return OpenAIProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=AppConfig(
            ui=UIConfig(default_provider="openai"),
            providers={
                "openai": ProviderSettings(
                    default_model="gpt-test",
                    base_url="https://api.openai.test/v1",
                )
            },
        ),
        provider_factory=openai_provider_factory,
        api_key_getter=lambda provider_id: "secret",
        rate_card={"gpt-test": ModelPricing(input_per_mtok=1.0, output_per_mtok=2.0)},
    )
    service.init()
    conversation = service.create_conversation()

    events = [event async for event in service.send_message(conversation.id, "hello")]
    messages = db.list_messages(conversation.id, db_path)

    assert events[-1].cache_creation_5m_input_tokens == 0
    assert events[-1].cache_creation_1h_input_tokens == 0
    assert events[-1].cache_read_input_tokens == 0
    assert messages[1].cache_creation_5m_input_tokens is None
    assert messages[1].cache_creation_1h_input_tokens is None
    assert messages[1].cache_read_input_tokens is None


def test_ensure_conversation_creates_default_when_empty(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()

    conversation = service.ensure_conversation()

    assert conversation.title == "New chat"
    assert conversation.provider_id == "anthropic"
    assert conversation.model == "claude-test"
    assert conversation.buddy_id is not None
    assert conversation.prompt_version_id is not None


def test_default_buddy_uses_configured_provider_and_model(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()

    buddy = service.default_buddy()

    assert buddy.provider_id == "anthropic"
    assert buddy.model == "claude-test"
    assert buddy.prompt_version_id is not None
    assert buddy in service.list_buddies()


def test_init_seeds_buddies_for_configured_provider_defaults(tmp_path: Path) -> None:
    service = ChatService(
        db_path=tmp_path / "chat.db",
        app_config=default_config(),
    )

    service.init()

    assert {(buddy.provider_id, buddy.model) for buddy in service.list_buddies()} >= {
        ("anthropic", "claude-fable-5"),
        ("anthropic", "claude-opus-4-8"),
        ("openai", "gpt-5"),
        ("mistral", "mistral-small-2603"),
        ("xai", "grok-4.3"),
    }


def test_buddy_memory_status_reports_empty_on_missing_row(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    buddy = service.default_buddy()

    status = service.buddy_memory_status(buddy.id)

    assert status.has_memory is False
    assert status.enabled is True
    assert status.suppressed is False
    assert status.label == "memory empty"


def test_buddy_memory_status_tracks_enabled_and_suppressed(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(db_path=db_path, app_config=app_config())
    service.init()
    buddy = service.default_buddy()
    db.upsert_buddy_memory(buddy.id, "Remember this.", path=db_path)

    enabled = service.buddy_memory_status(buddy.id)
    disabled = service.set_buddy_memory_enabled(buddy.id, False)
    db.set_buddy_memory_suppressed(buddy.id, True, db_path)
    suppressed = service.buddy_memory_status(buddy.id)

    assert enabled.label == "memory on"
    assert disabled.label == "memory off"
    assert suppressed.label == "memory suppressed"


def test_clear_buddy_memory_forgets_text_and_reports_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(db_path=db_path, app_config=app_config())
    service.init()
    buddy = service.default_buddy()
    db.upsert_buddy_memory(buddy.id, "Remember this.", path=db_path)

    status = service.clear_buddy_memory(buddy.id)

    assert status.label == "memory empty"
    memory = db.get_buddy_memory(buddy.id, db_path)
    assert memory is not None
    assert memory.memory_text == ""


@pytest.mark.asyncio
async def test_distill_buddy_memory_delegates_service_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    config = app_config()
    service = ChatService(
        db_path=db_path,
        app_config=config,
        provider_factory=provider_factory,
        api_key_getter=lambda provider_id: "secret",
        rate_card={
            "claude-test": ModelPricing(input_per_mtok=1.0, output_per_mtok=2.0)
        },
    )
    service.init()
    buddy = service.default_buddy()
    seen: dict[str, object] = {}

    async def fake_distiller(**kwargs: object) -> DistillResult:
        seen.update(kwargs)
        return DistillResult(
            buddy_id=buddy.id,
            status="noop",
            batches=0,
            memory_text="",
        )

    async def fake_run_memory_distiller(
        buddy_id: str,
        **kwargs: object,
    ) -> DistillResult:
        seen["buddy_id"] = buddy_id
        return await fake_distiller(**kwargs)

    monkeypatch.setattr("aol_llm.chat.run_memory_distiller", fake_run_memory_distiller)

    result = await service.distill_buddy_memory(buddy.id, mode="refactor")

    assert result.status == "noop"
    assert seen["buddy_id"] == buddy.id
    assert seen["mode"] == "refactor"
    assert seen["db_path"] == db_path
    assert seen["app_config"] == config
    assert seen["provider_factory"] == provider_factory
    assert "api_key_getter" in seen
    assert seen["rate_card"] == {
        "claude-test": ModelPricing(input_per_mtok=1.0, output_per_mtok=2.0)
    }


def test_init_does_not_recreate_archived_default_buddy(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(db_path=db_path, app_config=app_config())
    service.init()
    buddy = service.default_buddy()
    db.update_buddy(buddy.id, db_path, archived=True)

    reloaded = ChatService(db_path=db_path, app_config=app_config())
    reloaded.init()

    matching_buddies = [
        candidate
        for candidate in db.list_buddies(include_archived=True, path=db_path)
        if candidate.provider_id == "anthropic" and candidate.model == "claude-test"
    ]

    assert len(matching_buddies) == 1
    assert matching_buddies[0].archived is True
    assert all(
        (buddy.provider_id, buddy.model) != ("anthropic", "claude-test")
        for buddy in reloaded.list_buddies()
    )


def test_create_conversation_for_buddy_copies_buddy_state(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    buddy = db.ensure_buddy("anthropic", "claude-custom", tmp_path / "chat.db")

    conversation = service.create_conversation_for_buddy(buddy.id)

    assert conversation.buddy_id == buddy.id
    assert conversation.provider_id == buddy.provider_id
    assert conversation.model == buddy.model
    assert conversation.prompt_version_id == buddy.prompt_version_id


def test_ensure_conversation_for_buddy_reuses_latest_chat(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    buddy = service.default_buddy()
    first = service.create_conversation_for_buddy(buddy.id)
    latest = service.create_conversation_for_buddy(buddy.id)

    ensured = service.ensure_conversation_for_buddy(buddy.id)

    assert ensured == latest
    assert ensured != first
    assert service.list_conversations_for_buddy(buddy.id) == [latest, first]


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


def test_switch_model_preserves_conversation_a_way(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(db_path=db_path, app_config=app_config())
    service.init()
    conversation = service.create_conversation()
    custom = service.update_system_prompt(conversation.id, "Use the red door.")
    destination_buddy = db.ensure_buddy("anthropic", "claude-new", db_path)

    switched = service.switch_model(custom.id, "anthropic", "claude-new")

    assert switched.model == "claude-new"
    assert switched.buddy_id == destination_buddy.id
    assert switched.prompt_version_id == custom.prompt_version_id


def test_switch_model_uses_buddy_prompt_when_conversation_has_none(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    service = ChatService(db_path=db_path, app_config=app_config())
    service.init()
    conversation = db.create_conversation(
        "Legacy",
        "anthropic",
        "claude-test",
        path=db_path,
    )
    destination_buddy = db.ensure_buddy("anthropic", "claude-new", db_path)

    switched = service.switch_model(conversation.id, "anthropic", "claude-new")

    assert conversation.prompt_version_id is None
    assert switched.buddy_id == destination_buddy.id
    assert switched.prompt_version_id == destination_buddy.prompt_version_id


def test_rename_buddy_updates_display_name(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    buddy = service.default_buddy()

    renamed = service.rename_buddy(buddy.id, "Threshold")

    assert renamed.name == "Threshold"
    assert renamed.screen_name == "Threshold"
    assert service.get_buddy(buddy.id).screen_name == "Threshold"


def test_rename_buddy_rejects_blank_name(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    buddy = service.default_buddy()

    with pytest.raises(ValueError, match="buddy name cannot be empty"):
        service.rename_buddy(buddy.id, " ")


def test_conversation_reply_name_follows_buddy_rename(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()
    buddy_id = conversation.buddy_id
    assert buddy_id is not None

    service.rename_buddy(buddy_id, "Threshold")

    assert service.conversation_reply_name(conversation.id) == "Threshold"


def test_conversation_reply_name_override_can_be_set_and_cleared(
    tmp_path: Path,
) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()
    buddy_id = conversation.buddy_id
    assert buddy_id is not None
    service.rename_buddy(buddy_id, "Threshold")

    updated = service.update_conversation_reply_name(conversation.id, "  Oracle  ")

    assert updated.assistant_name == "Oracle"
    assert service.conversation_reply_name(updated.id) == "Oracle"

    cleared = service.update_conversation_reply_name(conversation.id, "   ")

    assert cleared.assistant_name is None
    assert service.conversation_reply_name(cleared.id) == "Threshold"


def test_model_choices_include_current_anthropic_models(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())

    assert [
        (choice.provider_id, choice.model) for choice in service.model_choices()
    ] == [
        ("anthropic", "claude-test"),
        ("anthropic", "claude-fable-5"),
        ("anthropic", "claude-opus-4-8"),
        ("anthropic", "claude-opus-4-7"),
        ("anthropic", "claude-sonnet-4-6"),
        ("anthropic", "claude-sonnet-4-5-20250929"),
    ]


def test_model_choices_include_default_mistral_small() -> None:
    service = ChatService(app_config=default_config())

    assert ("mistral", "mistral-small-2603") in [
        (choice.provider_id, choice.model) for choice in service.model_choices()
    ]


def test_model_choices_include_default_xai_grok() -> None:
    service = ChatService(app_config=default_config())

    assert ("xai", "grok-4.3") in [
        (choice.provider_id, choice.model) for choice in service.model_choices()
    ]


def test_prompt_cache_setting_defaults_off_and_can_toggle(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()

    assert service.prompt_cache_mode() == "off"
    assert service.prompt_cache_enabled() is False

    service.set_prompt_cache_mode("5m")
    assert service.prompt_cache_mode() == "5m"
    assert service.prompt_cache_enabled() is True

    service.set_prompt_cache_mode("1h")
    assert service.prompt_cache_mode() == "1h"
    assert service.prompt_cache_enabled() is True

    service.set_prompt_cache_mode("off")
    assert service.prompt_cache_mode() == "off"
    assert service.prompt_cache_enabled() is False

    service.set_prompt_cache_enabled(True)
    assert service.prompt_cache_mode() == "1h"


@pytest.mark.asyncio
async def test_send_message_passes_prompt_cache_for_anthropic(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_cache_ttls: list[str | None] = []

    class CacheProvider:
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
            del messages, system, max_output_tokens, temperature
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def cache_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        seen_cache_ttls.append(prompt_cache_ttl)
        return CacheProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=cache_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    service.set_prompt_cache_mode("1h")
    conversation = service.create_conversation()

    _ = [event async for event in service.send_message(conversation.id, "hello")]

    assert seen_cache_ttls == ["1h"]


def test_update_system_prompt_sets_and_clears_prompt(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=app_config())
    service.init()
    conversation = service.create_conversation()

    updated = service.update_system_prompt(conversation.id, "  Be precise.  ")
    cleared = service.update_system_prompt(conversation.id, "   ")

    assert updated.system_prompt == "Be precise."
    assert cleared.system_prompt is None
    assert updated.prompt_version_id is not None
    assert (
        cleared.prompt_version_id == db.default_prompt_version(tmp_path / "chat.db").id
    )


@pytest.mark.asyncio
async def test_legacy_system_prompt_fallback_when_no_prompt_version(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_systems: list[str | None] = []

    class LegacyProvider:
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
            del messages, max_output_tokens, temperature
            seen_systems.append(system)
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def legacy_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return LegacyProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=legacy_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = db.create_conversation(
        "Legacy",
        "anthropic",
        "claude-test",
        system_prompt="Legacy prompt.",
        path=db_path,
    )

    _ = [event async for event in service.send_message(conversation.id, "hello")]

    assert seen_systems == ["Legacy prompt."]


@pytest.mark.asyncio
async def test_send_message_injects_buddy_memory_after_a_way(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_systems: list[str | None] = []

    class MemoryProvider:
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
            del messages, max_output_tokens, temperature
            seen_systems.append(system)
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def memory_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return MemoryProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=memory_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = service.create_conversation()
    conversation = service.update_system_prompt(conversation.id, "Be concise.")
    assert conversation.buddy_id is not None
    db.upsert_buddy_memory(
        conversation.buddy_id,
        "Maria and this buddy are building prompt memory.",
        path=db_path,
    )

    _ = [event async for event in service.send_message(conversation.id, "hello")]

    assert len(seen_systems) == 1
    system = seen_systems[0]
    assert system is not None
    assert system.index("Be concise.") < system.index(MEMORY_BLOCK_HEADING)
    assert "Maria and this buddy are building prompt memory." in system


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("memory_text", "enabled", "suppressed"),
    [
        ("Persistent memory.", False, False),
        ("  \n", True, False),
        ("Persistent memory.", True, True),
    ],
)
async def test_send_message_skips_non_injectable_memory(
    tmp_path: Path,
    memory_text: str,
    enabled: bool,
    suppressed: bool,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_systems: list[str | None] = []

    class MemoryProvider:
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
            del messages, max_output_tokens, temperature
            seen_systems.append(system)
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def memory_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return MemoryProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=memory_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = service.create_conversation()
    conversation = service.update_system_prompt(conversation.id, "Be concise.")
    assert conversation.buddy_id is not None
    db.upsert_buddy_memory(
        conversation.buddy_id,
        memory_text,
        path=db_path,
        enabled=enabled,
        suppress_injection=suppressed,
    )

    _ = [event async for event in service.send_message(conversation.id, "hello")]

    assert seen_systems == ["Be concise."]


@pytest.mark.asyncio
async def test_openai_compatible_send_receives_flattened_memory_prefix(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_systems: list[str | None] = []

    class OpenAIProvider:
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
            del messages, max_output_tokens, temperature
            seen_systems.append(system)
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def openai_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return OpenAIProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=AppConfig(
            ui=UIConfig(default_provider="openai"),
            providers={
                "openai": ProviderSettings(
                    default_model="gpt-test",
                    base_url="https://api.openai.test/v1",
                )
            },
        ),
        provider_factory=openai_provider_factory,
        api_key_getter=lambda provider_id: "secret",
    )
    service.init()
    conversation = service.create_conversation()
    conversation = service.update_system_prompt(conversation.id, "Be concise.")
    assert conversation.buddy_id is not None
    db.upsert_buddy_memory(
        conversation.buddy_id,
        "Remember the atlas work.",
        path=db_path,
    )

    _ = [event async for event in service.send_message(conversation.id, "hello")]

    system = seen_systems[0]
    assert system is not None
    assert system == "\n\n".join(system.split("\n\n"))
    assert system.index("Be concise.") < system.index(MEMORY_BLOCK_HEADING)
    assert "Remember the atlas work." in system


@pytest.mark.asyncio
async def test_memory_is_frozen_for_conversation_within_service_instance(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    seen_systems: list[str | None] = []

    class MemoryProvider:
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
            del messages, max_output_tokens, temperature
            seen_systems.append(system)
            yield StreamChunk(text="ok", done=False)
            yield StreamChunk(
                text="",
                done=True,
                usage=TokenUsage(input_tokens=1, output_tokens=1, model=model),
            )

    def memory_provider_factory(
        config: ProviderConfig,
        api_key: str | None,
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
        return MemoryProvider(config, api_key)

    service = ChatService(
        db_path=db_path,
        app_config=app_config(),
        provider_factory=memory_provider_factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    conversation = service.create_conversation()
    conversation = service.update_system_prompt(conversation.id, "Be concise.")
    assert conversation.buddy_id is not None
    db.upsert_buddy_memory(conversation.buddy_id, "First memory.", path=db_path)

    _ = [event async for event in service.send_message(conversation.id, "hello")]
    db.upsert_buddy_memory(conversation.buddy_id, "Second memory.", path=db_path)
    _ = [event async for event in service.send_message(conversation.id, "again")]

    assert len(seen_systems) == 2
    assert "First memory." in (seen_systems[0] or "")
    assert "First memory." in (seen_systems[1] or "")
    assert "Second memory." not in (seen_systems[1] or "")


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
        prompt_cache_ttl: str | None = None,
    ) -> Provider:
        del prompt_cache_ttl
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
