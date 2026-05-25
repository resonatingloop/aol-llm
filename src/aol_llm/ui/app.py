"""Textual app shell for AOL-LLM."""

from textual.app import App

from aol_llm.chat import ChatService
from aol_llm.core.errors import ProviderError
from aol_llm.core.types import Conversation
from aol_llm.ui.modals import ConfirmModal, ModelPickerModal
from aol_llm.ui.screens import MainScreen, SettingsScreen
from aol_llm.ui.widgets import ChatTranscript, Composer, ConversationList, StatusBar


class AOLLLMApp(App[None]):
    CSS = """
    Screen {
        background: $background;
    }

    #main-layout {
        height: 1fr;
    }

    #workbench {
        height: 1fr;
    }

    #sidebar {
        width: 28;
        min-width: 24;
        border-right: solid $panel;
        padding: 1;
    }

    #chat-pane {
        width: 1fr;
    }

    #chat-transcript {
        height: 1fr;
        padding: 1 2;
    }

    #transcript-body {
        height: 1fr;
    }

    #composer {
        height: 7;
        border-top: solid $panel;
    }

    #composer-input {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
    }

    #status-row {
        height: 1;
    }

    #status-model {
        width: 1fr;
    }

    #status-usage {
        width: auto;
    }

    .panel-title {
        text-style: bold;
    }

    .message {
        padding: 0 0 1 0;
    }

    #settings-layout {
        padding: 1 2;
    }

    .modal-actions {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("ctrl+n", "new_conversation", "New"),
        ("ctrl+enter", "send_message", "Send"),
        ("ctrl+m", "open_model_picker", "Model"),
        ("ctrl+comma", "open_settings", "Settings"),
        ("ctrl+r", "retry_last", "Retry"),
        ("ctrl+e", "export_current_chat", "Export"),
        ("ctrl+d", "delete_current_chat", "Delete"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, chat_service: ChatService | None = None) -> None:
        super().__init__()
        self._chat_service = chat_service or ChatService()
        self._current_conversation: Conversation | None = None
        self._sending = False

    async def on_mount(self) -> None:
        await self.push_screen(MainScreen())
        self._chat_service.init()
        self._current_conversation = self._chat_service.ensure_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()

    def action_new_conversation(self) -> None:
        self._current_conversation = self._chat_service.create_conversation()
        self._refresh_conversation_list()
        self._refresh_status_model()

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

    def action_open_model_picker(self) -> None:
        self.push_screen(ModelPickerModal())

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_retry_last(self) -> None:
        self.notify("Retry")

    def action_export_current_chat(self) -> None:
        self.notify("Export")

    def action_delete_current_chat(self) -> None:
        self.push_screen(ConfirmModal("Delete current chat?"))

    def _refresh_conversation_list(self) -> None:
        self.screen.query_one(ConversationList).set_conversations(
            self._chat_service.list_conversations()
        )

    def _refresh_status_model(self) -> None:
        if self._current_conversation is None:
            return
        self.screen.query_one(StatusBar).set_model(
            self._current_conversation.provider_id,
            self._current_conversation.model,
        )


def run() -> None:
    AOLLLMApp().run()
