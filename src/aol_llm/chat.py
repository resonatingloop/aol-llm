"""Chat orchestration between storage, config, secrets, and providers."""

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from aol_llm.config import AppConfig, load_config
from aol_llm.core.pricing import ModelPricing, estimate_cost_usd
from aol_llm.core.types import Conversation, ProviderConfig, ProviderKind
from aol_llm.providers.base import Provider
from aol_llm.providers.registry import build_provider
from aol_llm.secrets import get_api_key
from aol_llm.storage import db

ProviderFactory = Callable[[ProviderConfig, str | None], Provider]
ApiKeyGetter = Callable[[str], str | None]


@dataclass(frozen=True)
class ChatEvent:
    text: str
    done: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


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

    async def send_message(
        self,
        conversation_id: str,
        content: str,
    ) -> AsyncIterator[ChatEvent]:
        conversation = db.get_conversation(conversation_id, self._db_path)
        db.add_message(conversation_id, "user", content, path=self._db_path)
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
            available_models=[settings.default_model],
        )
