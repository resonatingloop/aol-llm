"""Textual screens for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, Static

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


class SettingsScreen(Screen[None]):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("f1", "app.pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="settings-layout"):
            yield Label("Settings", classes="panel-title")
            yield Input(placeholder="provider id", id="provider-id")
            yield Input(placeholder="default model", id="default-model")
            yield Input(placeholder="base url", id="base-url")
            yield Input(placeholder="api key", password=True, id="api-key")
            yield Static(
                "settings editor is not wired yet; edit config/keyring manually",
                id="settings-status",
            )
        yield Footer()
