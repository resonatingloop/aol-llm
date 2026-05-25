"""Chat orchestration between storage, config, secrets, and providers."""

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from aol_llm.config import AppConfig, load_config
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd
from aol_llm.core.types import Conversation, Message, ProviderConfig, ProviderKind
from aol_llm.export import write_export
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import build_provider
from aol_llm.secrets import get_api_key
from aol_llm.storage import db

ProviderFactory = Callable[[ProviderConfig, str | None], Provider]
ApiKeyGetter = Callable[[str], str | None]
DEFAULT_PROVIDER_MODELS = {
    "anthropic": ["claude-opus-4-7", "claude-sonnet-4-5-20250929"],
    "openai": ["gpt-5"],
}


@dataclass(frozen=True)
class ChatEvent:
    text: str
    done: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class ModelChoice:
    provider_id: str
    model: str


class ChatService:
    def __init__(
        self,
        db_path: Path | None = None,
        app_config: AppConfig | None = None,
        provider_factory: ProviderFactory = build_provider,
        api_key_getter: ApiKeyGetter = get_api_key,
        rate_card: Mapping[str, ModelPricing] | None = None,
    ) -> None:
        self._db_path = db_path
        self._config = app_config or load_config()
        self._provider_factory = provider_factory
        self._api_key_getter = api_key_getter
        self._rate_card = rate_card or {}

    def init(self) -> None:
        db.init_db(self._db_path)

    def ensure_conversation(self) -> Conversation:
        conversations = db.list_conversations(path=self._db_path)
        if conversations:
            return conversations[0]

        return self.create_conversation()

    def create_conversation(self) -> Conversation:
        provider_id = self._config.ui.default_provider
        settings = self._config.providers[provider_id]
        return db.create_conversation(
            title="New chat",
            provider_id=provider_id,
            model=settings.default_model,
            path=self._db_path,
        )

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

    def update_system_prompt(
        self,
        conversation_id: str,
        system_prompt: str,
    ) -> Conversation:
        clean_prompt = system_prompt.strip() or None
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            system_prompt=clean_prompt,
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
        if not model.strip():
            raise ValueError("model cannot be empty")
        return db.update_conversation(
            conversation_id,
            path=self._db_path,
            provider_id=provider_id,
            model=model.strip(),
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
        return write_export(conversation, messages, export_dir, format)

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
        )
        assistant_text = ""

        async for chunk in provider.stream(
            messages=messages,
            system=conversation.system_prompt,
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
            )
            return

    def messages(self, conversation_id: str) -> list[Message]:
        return db.list_messages(conversation_id, self._db_path)

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

    def _default_export_dir(self) -> Path:
        if self._db_path is not None:
            return self._db_path.parent / "exports"
        from aol_llm.config import user_data_dir

        return user_data_dir() / "exports"


def _provider_models(provider_id: str, default_model: str) -> list[str]:
    models = [default_model]
    for model in DEFAULT_PROVIDER_MODELS.get(provider_id, []):
        if model not in models:
            models.append(model)
    return models
