"""Textual app shell for AOL-LLM."""

from textual.app import App

from aol_llm.ui.modals import ConfirmModal, ModelPickerModal
from aol_llm.ui.screens import MainScreen, SettingsScreen


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

    async def on_mount(self) -> None:
        await self.push_screen(MainScreen())

    def action_new_conversation(self) -> None:
        self.notify("New conversation")

    def action_send_message(self) -> None:
        self.notify("Send")

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


def run() -> None:
    AOLLLMApp().run()
