"""Chat orchestration between storage, config, secrets, and providers."""

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aol_llm.config import AppConfig, load_config
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd, load_rate_card
from aol_llm.core.types import (
    Buddy,
    Conversation,
    Message,
    ProviderConfig,
    ProviderKind,
)
from aol_llm.export import write_export
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import build_provider
from aol_llm.secrets import get_api_key
from aol_llm.storage import db

PromptCacheTTL = Literal["5m", "1h"]
ProviderFactory = Callable[
    [ProviderConfig, str | None, PromptCacheTTL | None], Provider
]
ApiKeyGetter = Callable[[str], str | None]
PROMPT_CACHE_SETTING = "anthropic_prompt_cache_enabled"
PromptCacheMode = Literal["off", "5m", "1h"]
PROMPT_CACHE_MODES: set[PromptCacheMode] = {"off", "5m", "1h"}
DEFAULT_PROVIDER_MODELS = {
    "anthropic": [
        "claude-fable-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929",
    ],
    "openai": ["gpt-5"],
    "mistral": ["mistral-small-2603"],
    "xai": ["grok-4.3"],
}


@dataclass(frozen=True)
class ChatEvent:
    text: str
    done: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cache_creation_5m_input_tokens: int = 0
    cache_creation_1h_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class ModelChoice:
    provider_id: str
    model: str


class ChatService:
    def __init__(
        self,
        db_path: Path | None = None,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
        provider_factory: ProviderFactory = build_provider,
        api_key_getter: ApiKeyGetter = get_api_key,
        rate_card: Mapping[str, ModelPricing] | None = None,
    ) -> None:
        self._db_path = db_path
        self._config = app_config or load_config(config_path)
        self._provider_factory = provider_factory
        self._api_key_getter = api_key_getter
        self._rate_card = load_rate_card() if rate_card is None else rate_card

    def init(self) -> None:
        db.init_db(self._db_path)
        self._ensure_configured_buddies()

    def ensure_conversation(self) -> Conversation:
        return self.ensure_conversation_for_buddy(self.default_buddy().id)

    def default_buddy(self) -> Buddy:
        provider_id = self._config.ui.default_provider
        settings = self._config.providers[provider_id]
        return db.ensure_buddy(provider_id, settings.default_model, self._db_path)

    def list_buddies(self) -> list[Buddy]:
        return db.list_buddies(path=self._db_path)

    def get_buddy(self, buddy_id: str) -> Buddy:
        return db.get_buddy(buddy_id, self._db_path)

    def list_conversations_for_buddy(self, buddy_id: str) -> list[Conversation]:
        return db.list_conversations_for_buddy(buddy_id, path=self._db_path)

    def create_conversation(self) -> Conversation:
        return self.create_conversation_for_buddy(self.default_buddy().id)

    def create_conversation_for_buddy(self, buddy_id: str) -> Conversation:
        buddy = db.get_buddy(buddy_id, self._db_path)
        return db.create_conversation(
            title="New chat",
            provider_id=buddy.provider_id,
            model=buddy.model,
            buddy_id=buddy.id,
            prompt_version_id=buddy.prompt_version_id,
            path=self._db_path,
        )

    def ensure_conversation_for_buddy(self, buddy_id: str) -> Conversation:
        conversations = self.list_conversations_for_buddy(buddy_id)
        if conversations:
            return conversations[0]
        return self.create_conversation_for_buddy(buddy_id)

    def list_conversations(self) -> list[Conversation]:
        return db.list_conversations(path=self._db_path)

    def get_conversation(self, conversation_id: str) -> Conversation:
        return db.get_conversation(conversation_id, self._db_path)

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("conversation title cannot be empty")
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            title=clean_title,
        )

    def rename_buddy(self, buddy_id: str, name: str) -> Buddy:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("buddy name cannot be empty")
        return db.update_buddy(
            buddy_id,
            path=self._db_path,
            name=clean_name,
            screen_name=clean_name,
        )

    def conversation_reply_name(self, conversation_id: str) -> str:
        return self._resolve_reply_name(
            db.get_conversation(conversation_id, self._db_path)
        )

    def update_conversation_reply_name(
        self,
        conversation_id: str,
        name: str,
    ) -> Conversation:
        clean_name = name.strip() or None
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            assistant_name=clean_name,
        )

    def update_system_prompt(
        self,
        conversation_id: str,
        system_prompt: str,
    ) -> Conversation:
        clean_prompt = system_prompt.strip() or None
        prompt_version_id = self._create_away_message_version(clean_prompt)
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            system_prompt=clean_prompt,
            prompt_version_id=prompt_version_id,
        )

    def archive_conversation(self, conversation_id: str) -> Conversation:
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            archived=True,
        )

    def delete_conversation(self, conversation_id: str) -> None:
        db.delete_conversation(conversation_id, self._db_path)

    def switch_model(
        self,
        conversation_id: str,
        provider_id: str,
        model: str,
    ) -> Conversation:
        if provider_id not in self._config.providers:
            raise KeyError(f"unknown provider config: {provider_id}")
        clean_model = model.strip()
        if not clean_model:
            raise ValueError("model cannot be empty")
        conversation = db.get_conversation(conversation_id, self._db_path)
        buddy = db.ensure_buddy(provider_id, clean_model, self._db_path)
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            provider_id=provider_id,
            model=clean_model,
            buddy_id=buddy.id,
            prompt_version_id=conversation.prompt_version_id or buddy.prompt_version_id,
        )

    def model_choices(self) -> list[ModelChoice]:
        choices = []
        for provider_id, settings in sorted(self._config.providers.items()):
            for model in _provider_models(provider_id, settings.default_model):
                choices.append(ModelChoice(provider_id=provider_id, model=model))
        return choices

    def export_conversation(
        self,
        conversation_id: str,
        format: str = "markdown",
        directory: Path | None = None,
    ) -> Path:
        conversation = db.get_conversation(conversation_id, self._db_path)
        messages = db.list_messages(conversation_id, self._db_path)
        export_dir = directory or self._default_export_dir()
        return write_export(
            conversation,
            messages,
            export_dir,
            format,
            reply_name=self._resolve_reply_name(conversation),
        )

    def set_prompt_cache_enabled(self, enabled: bool) -> None:
        self.set_prompt_cache_mode("1h" if enabled else "off")

    def prompt_cache_enabled(self) -> bool:
        return self.prompt_cache_mode() != "off"

    def set_prompt_cache_mode(self, mode: PromptCacheMode) -> None:
        db.set_app_setting(PROMPT_CACHE_SETTING, mode, self._db_path)

    def prompt_cache_mode(self) -> PromptCacheMode:
        value = db.get_app_setting(PROMPT_CACHE_SETTING, self._db_path)
        if value == "1":
            return "1h"
        if value == "0" or value is None:
            return "off"
        if value in PROMPT_CACHE_MODES:
            return value
        return "off"

    async def send_message(
        self,
        conversation_id: str,
        content: str,
    ) -> AsyncIterator[ChatEvent]:
        db.add_message(conversation_id, "user", content, path=self._db_path)
        async for event in self.stream_response(conversation_id):
            yield event

    async def retry_last_response(
        self,
        conversation_id: str,
    ) -> AsyncIterator[ChatEvent]:
        self.prepare_retry(conversation_id)
        async for event in self.stream_response(conversation_id):
            yield event

    def prepare_retry(self, conversation_id: str) -> None:
        messages = db.list_messages(conversation_id, self._db_path)
        if not messages:
            raise ValueError("cannot retry an empty conversation")
        if messages[-1].role == "assistant":
            db.delete_message(messages[-1].id, self._db_path)
            messages = messages[:-1]
        if not messages or messages[-1].role != "user":
            raise ValueError("last message must be user-authored to retry")

    async def stream_response(
        self,
        conversation_id: str,
    ) -> AsyncIterator[ChatEvent]:
        async for event in self._stream_assistant(conversation_id):
            yield event

    async def _stream_assistant(
        self,
        conversation_id: str,
    ) -> AsyncIterator[ChatEvent]:
        conversation = db.get_conversation(conversation_id, self._db_path)
        messages = db.list_messages(conversation_id, self._db_path)
        provider_config = self._provider_config(conversation)
        provider = self._provider_factory(
            provider_config,
            self._api_key_getter(provider_config.id),
            self._prompt_cache_ttl(conversation),
        )
        system, prompt_version_id = self._resolve_system_prompt(conversation)
        assistant_text = ""

        async for chunk in provider.stream(
            messages=messages,
            system=system,
            model=conversation.model,
        ):
            if not chunk.done:
                assistant_text += chunk.text
                yield ChatEvent(text=chunk.text, done=False)
                continue

            usage = chunk.usage
            if usage is None:
                continue
            cost_usd = estimate_cost_usd(usage, self._rate_card)
            db.add_message(
                conversation_id,
                "assistant",
                assistant_text,
                path=self._db_path,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost_usd,
                prompt_version_id=prompt_version_id,
            )
            db.update_conversation(
                conversation_id,
                path=self._db_path,
                model=conversation.model,
            )
            yield ChatEvent(
                text="",
                done=True,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost_usd,
                cache_creation_5m_input_tokens=usage.cache_creation_5m_input_tokens,
                cache_creation_1h_input_tokens=usage.cache_creation_1h_input_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens,
            )
            return

    def messages(self, conversation_id: str) -> list[Message]:
        return db.list_messages(conversation_id, self._db_path)

    def _create_away_message_version(self, system_prompt: str | None) -> str:
        if system_prompt is None:
            return db.default_prompt_version(self._db_path).id
        prompt = db.create_prompt(
            name="Draft a-way Message",
            gloss="draft",
            core=system_prompt,
            path=self._db_path,
            status="draft",
        )
        version = db.create_prompt_version(
            prompt,
            path=self._db_path,
            note="created from conversation a-way edit",
        )
        db.update_prompt_current_version(prompt.id, version.id, self._db_path)
        return version.id

    def _resolve_system_prompt(
        self,
        conversation: Conversation,
    ) -> tuple[str | None, str | None]:
        if conversation.prompt_version_id is not None:
            try:
                version = db.get_prompt_version(
                    conversation.prompt_version_id,
                    self._db_path,
                )
            except KeyError:
                pass
            else:
                return version.core or None, version.id

        if conversation.buddy_id is not None:
            try:
                buddy = db.get_buddy(conversation.buddy_id, self._db_path)
            except KeyError:
                pass
            else:
                if buddy.prompt_version_id is not None:
                    version = db.get_prompt_version(
                        buddy.prompt_version_id,
                        self._db_path,
                    )
                    return version.core or None, version.id

        return conversation.system_prompt, None

    def _resolve_reply_name(self, conversation: Conversation) -> str:
        if conversation.assistant_name is not None:
            return conversation.assistant_name
        if conversation.buddy_id is not None:
            try:
                buddy = db.get_buddy(conversation.buddy_id, self._db_path)
            except KeyError:
                pass
            else:
                return buddy.screen_name or buddy.name
        return "assistant"

    def _provider_config(self, conversation: Conversation) -> ProviderConfig:
        settings = self._config.providers[conversation.provider_id]
        kind: ProviderKind = (
            "anthropic"
            if conversation.provider_id == "anthropic"
            else "openai_compatible"
        )
        return ProviderConfig(
            id=conversation.provider_id,
            kind=kind,
            display_name=conversation.provider_id,
            base_url=settings.base_url,
            keyring_service=f"aol-llm.{conversation.provider_id}",
            default_model=settings.default_model,
            available_models=_provider_models(
                conversation.provider_id,
                settings.default_model,
            ),
        )

    def _prompt_cache_ttl(
        self,
        conversation: Conversation,
    ) -> PromptCacheTTL | None:
        if conversation.provider_id != "anthropic":
            return None
        mode = self.prompt_cache_mode()
        if mode == "off":
            return None
        return mode

    def _default_export_dir(self) -> Path:
        if self._db_path is not None:
            return self._db_path.parent / "exports"
        from aol_llm.config import user_data_dir

        return user_data_dir() / "exports"

    def _ensure_configured_buddies(self) -> None:
        for provider_id, settings in self._config.providers.items():
            if not db.buddy_exists(provider_id, settings.default_model, self._db_path):
                db.ensure_buddy(provider_id, settings.default_model, self._db_path)


def _provider_models(provider_id: str, default_model: str) -> list[str]:
    models = [default_model]
    for model in DEFAULT_PROVIDER_MODELS.get(provider_id, []):
        if model not in models:
            models.append(model)
    return models
