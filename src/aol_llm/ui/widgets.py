"""Textual widgets for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, ListItem, ListView, Static, TextArea


class ConversationList(Static):
    def compose(self) -> ComposeResult:
        yield Label("Conversations", classes="panel-title")
        yield ListView(
            ListItem(Label("First chat")),
            ListItem(Label("Provider notes")),
            ListItem(Label("Scratchpad")),
            id="conversation-list",
        )


class ChatTranscript(Static):
    def compose(self) -> ComposeResult:
        yield Label("Transcript", classes="panel-title")
        with Vertical(id="transcript-body"):
            yield Static("user: hello", classes="message user-message")
            yield Static("assistant: ready", classes="message assistant-message")


class Composer(Static):
    def compose(self) -> ComposeResult:
        yield TextArea(id="composer-input")


class StatusBar(Static):
    def compose(self) -> ComposeResult:
        with Horizontal(id="status-row"):
            yield Static("anthropic / claude-sonnet-test", id="status-model")
            yield Static("input 0 / output 0 / $0.0000", id="status-usage")
