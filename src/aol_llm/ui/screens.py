"""Textual screens for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from aol_llm.ui.widgets import (
    BuddyList,
    ChatTranscript,
    Composer,
    ConversationList,
    StatusBar,
)


class MainScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-layout"):
            with Horizontal(id="workbench"):
                with Vertical(id="sidebar"):
                    yield BuddyList(id="buddy-pane")
                    yield ConversationList(id="chat-list-pane")
                with Vertical(id="chat-pane"):
                    yield ChatTranscript(id="chat-transcript")
                    yield Composer(id="composer")
            yield StatusBar(id="status-bar")
        yield Footer()


class SettingsScreen(Screen[str | None]):
    BINDINGS = [
        ("escape", "cancel", "Back"),
        ("f1", "cancel", "Back"),
    ]

    def __init__(self, assistant_name: str) -> None:
        super().__init__()
        self._assistant_name = assistant_name

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="settings-layout"):
            yield Label("Settings", classes="panel-title")
            yield Label("Assistant display name")
            yield Input(value=self._assistant_name, id="assistant-name")
            with Horizontal(classes="modal-actions"):
                yield Button("Save", id="save-settings", variant="primary")
            yield Static(
                "provider config and API keys are still edited manually",
                id="settings-status",
            )
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "assistant-name":
            self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self.dismiss(self.query_one("#assistant-name", Input).value)

    def action_cancel(self) -> None:
        self.dismiss(None)
