"""Textual widgets for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static, TextArea

from aol_llm.core.types import Conversation


class ConversationList(Static):
    def compose(self) -> ComposeResult:
        yield Label("Conversations", classes="panel-title")
        yield ListView(id="conversation-list")

    def set_conversations(self, conversations: list[Conversation]) -> None:
        list_view = self.query_one("#conversation-list", ListView)
        list_view.clear()
        for conversation in conversations:
            list_view.append(ListItem(Label(conversation.title)))


class ChatTranscript(Static):
    def compose(self) -> ComposeResult:
        yield Label("Transcript", classes="panel-title")
        yield VerticalScroll(id="transcript-body")

    def append_message(self, role: str, content: str) -> Static:
        body = self.query_one("#transcript-body", VerticalScroll)
        message = Static(f"{role}: {content}", classes=f"message {role}-message")
        body.mount(message)
        body.scroll_end(animate=False)
        return message

    def clear_messages(self) -> None:
        body = self.query_one("#transcript-body", VerticalScroll)
        body.remove_children()

    def scroll_to_end(self) -> None:
        self.query_one("#transcript-body", VerticalScroll).scroll_end(animate=False)


class Composer(Static):
    def compose(self) -> ComposeResult:
        yield TextArea(id="composer-input")

    def text(self) -> str:
        return self.query_one("#composer-input", TextArea).text

    def clear(self) -> None:
        self.query_one("#composer-input", TextArea).clear()


class StatusBar(Static):
    def compose(self) -> ComposeResult:
        with Horizontal(id="status-row"):
            yield Static("anthropic / claude-sonnet-test", id="status-model")
            yield Static("input 0 / output 0 / $0.0000", id="status-usage")

    def set_model(self, provider_id: str, model: str) -> None:
        self.query_one("#status-model", Static).update(f"{provider_id} / {model}")

    def set_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cost_usd = cost_usd
        self.query_one("#status-usage", Static).update(
            f"input {input_tokens} / output {output_tokens} / ${cost_usd:.4f}"
        )

    def add_usage(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        current_input = getattr(self, "_input_tokens", 0) + (input_tokens or 0)
        current_output = getattr(self, "_output_tokens", 0) + (output_tokens or 0)
        current_cost = getattr(self, "_cost_usd", 0.0) + (cost_usd or 0.0)
        self._input_tokens = current_input
        self._output_tokens = current_output
        self._cost_usd = current_cost
        self.query_one("#status-usage", Static).update(
            f"input {current_input} / output {current_output} / ${current_cost:.4f}"
        )
