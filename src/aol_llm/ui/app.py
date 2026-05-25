"""Textual app shell for AOL-LLM."""

from collections.abc import AsyncIterator

from textual.app import App
from textual.widgets import ListView

from aol_llm.chat import ChatEvent, ChatService, ModelChoice
from aol_llm.core.errors import ProviderError
from aol_llm.core.types import Conversation
from aol_llm.ui.modals import (
    ConfirmModal,
    ExportFormatModal,
    ModelPickerModal,
    RenameModal,
    SystemPromptModal,
)
from aol_llm.ui.screens import MainScreen, SettingsScreen
from aol_llm.ui.styles import APP_BINDINGS, APP_CSS
from aol_llm.ui.widgets import ChatTranscript, Composer, ConversationList, StatusBar


class AOLLLMApp(App[None]):
    CSS = APP_CSS
    BINDINGS = APP_BINDINGS

    def __init__(self, chat_service: ChatService | None = None) -> None:
        super().__init__()
        self._chat_service = chat_service or ChatService()
        self._current_conversation: Conversation | None = None
        self._conversation_ids: list[str] = []
        self._sending = False

    async def on_mount(self) -> None:
        await self.push_screen(MainScreen())
        self._chat_service.init()
        self._current_conversation = self._chat_service.ensure_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()
        self._load_current_transcript()

    def action_new_conversation(self) -> None:
        self._current_conversation = self._chat_service.create_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()
        self._load_current_transcript()

    async def action_send_message(self) -> None:
        if self._sending or self._current_conversation is None:
            return

        composer = self.screen.query_one(Composer)
        content = composer.text().strip()
        if not content:
            return

        self._sending = True
        composer.clear()
        transcript = self.screen.query_one(ChatTranscript)
        transcript.append_message("user", content)
        assistant_message = transcript.append_message("assistant", "")
        assistant_text = ""

        try:
            async for event in self._chat_service.send_message(
                self._current_conversation.id,
                content,
            ):
                if not event.done:
                    assistant_text += event.text
                    assistant_message.update(f"assistant: {assistant_text}")
                    transcript.scroll_to_end()
                    continue
                self.screen.query_one(StatusBar).add_usage(
                    event.input_tokens,
                    event.output_tokens,
                    event.cost_usd,
                )
        except ProviderError as error:
            assistant_message.update(f"assistant: {error}")
            self.notify(str(error), severity="error")
        finally:
            self._sending = False
            self._refresh_conversation_list()

    def action_rename_current_chat(self) -> None:
        if self._current_conversation is None:
            return
        self.push_screen(
            RenameModal(self._current_conversation.title),
            self._rename_current_chat,
        )

    def action_edit_system_prompt(self) -> None:
        if self._current_conversation is None:
            return
        self.push_screen(
            SystemPromptModal(self._current_conversation.system_prompt),
            self._update_system_prompt,
        )

    def action_open_model_picker(self) -> None:
        self.push_screen(
            ModelPickerModal(self._chat_service.model_choices()),
            self._switch_current_model,
        )

    def action_open_settings(self) -> None:
        if isinstance(self.screen, SettingsScreen):
            self.pop_screen()
            return
        self.push_screen(SettingsScreen())

    async def action_retry_last(self) -> None:
        if self._sending or self._current_conversation is None:
            return

        self._sending = True
        try:
            self._chat_service.prepare_retry(self._current_conversation.id)
            self._load_current_transcript()
            await self._stream_assistant_response(
                self._chat_service.stream_response(self._current_conversation.id)
            )
        except (ProviderError, ValueError) as error:
            self.notify(str(error), severity="error")
        finally:
            self._sending = False
            self._refresh_conversation_list()

    def action_export_current_chat(self) -> None:
        self.push_screen(ExportFormatModal(), self._export_current_chat)

    def action_archive_current_chat(self) -> None:
        self.push_screen(
            ConfirmModal("Archive current chat?"),
            self._archive_current_chat,
        )

    def action_delete_current_chat(self) -> None:
        self.push_screen(
            ConfirmModal("Delete current chat?"), self._delete_current_chat
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "conversation-list":
            return
        if event.index >= len(self._conversation_ids):
            return
        self._current_conversation = self._chat_service.get_conversation(
            self._conversation_ids[event.index]
        )
        self._refresh_status_model()
        self._load_current_transcript()

    def _rename_current_chat(self, title: str | None) -> None:
        if self._current_conversation is None or title is None:
            return
        try:
            self._current_conversation = self._chat_service.rename_conversation(
                self._current_conversation.id,
                title,
            )
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self._refresh_conversation_list()

    def _switch_current_model(self, choice: ModelChoice | None) -> None:
        if self._current_conversation is None or choice is None:
            return
        self._current_conversation = self._chat_service.switch_model(
            self._current_conversation.id,
            choice.provider_id,
            choice.model,
        )
        self._refresh_conversation_list()
        self._refresh_status_model()

    def _update_system_prompt(self, system_prompt: str | None) -> None:
        if self._current_conversation is None or system_prompt is None:
            return
        self._current_conversation = self._chat_service.update_system_prompt(
            self._current_conversation.id,
            system_prompt,
        )
        self.notify("System prompt updated")

    def _export_current_chat(self, format: str | None) -> None:
        if self._current_conversation is None or format is None:
            return
        path = self._chat_service.export_conversation(
            self._current_conversation.id,
            format,
        )
        self.notify(f"Exported {path}")

    def _archive_current_chat(self, confirmed: bool | None) -> None:
        if self._current_conversation is None or not confirmed:
            return
        self._chat_service.archive_conversation(self._current_conversation.id)
        self._current_conversation = self._chat_service.ensure_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()
        self._load_current_transcript()

    def _delete_current_chat(self, confirmed: bool | None) -> None:
        if self._current_conversation is None or not confirmed:
            return
        self._chat_service.delete_conversation(self._current_conversation.id)
        self._current_conversation = self._chat_service.ensure_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()
        self._load_current_transcript()

    def _refresh_conversation_list(self) -> None:
        conversations = self._chat_service.list_conversations()
        self._conversation_ids = [conversation.id for conversation in conversations]
        self.screen.query_one(ConversationList).set_conversations(conversations)

    def _refresh_status_model(self) -> None:
        if self._current_conversation is None:
            return
        self.screen.query_one(StatusBar).set_model(
            self._current_conversation.provider_id,
            self._current_conversation.model,
        )

    def _load_current_transcript(self) -> None:
        if self._current_conversation is None:
            return
        transcript = self.screen.query_one(ChatTranscript)
        transcript.clear_messages()
        messages = self._chat_service.messages(self._current_conversation.id)
        for message in messages:
            transcript.append_message(message.role, message.content)
        self.screen.query_one(StatusBar).set_usage(
            sum(message.input_tokens or 0 for message in messages),
            sum(message.output_tokens or 0 for message in messages),
            sum(message.cost_usd or 0.0 for message in messages),
        )

    async def _stream_assistant_response(
        self,
        events: AsyncIterator[ChatEvent],
    ) -> None:
        transcript = self.screen.query_one(ChatTranscript)
        assistant_message = transcript.append_message("assistant", "")
        assistant_text = ""
        async for event in events:
            if not event.done:
                assistant_text += event.text
                assistant_message.update(f"assistant: {assistant_text}")
                transcript.scroll_to_end()
                continue
            self.screen.query_one(StatusBar).add_usage(
                event.input_tokens,
                event.output_tokens,
                event.cost_usd,
            )


def run() -> None:
    AOLLLMApp().run()
