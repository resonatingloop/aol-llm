"""Textual widgets for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static, TextArea

from aol_llm.core.types import Buddy, Conversation


def format_usage_status(
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    cache_read_input_tokens: int = 0,
    cache_creation_5m_input_tokens: int = 0,
    cache_creation_1h_input_tokens: int = 0,
) -> str:
    return (
        f"input {input_tokens} / output {output_tokens} / "
        f"cache r {cache_read_input_tokens} "
        f"w5 {cache_creation_5m_input_tokens} "
        f"w1h {cache_creation_1h_input_tokens} / ${cost_usd:.4f}"
    )


class BuddyList(Static):
    def compose(self) -> ComposeResult:
        yield Label("Buddy List", classes="panel-title")
        yield ListView(id="buddy-list")

    def set_buddies(self, buddies: list[Buddy]) -> None:
        list_view = self.query_one("#buddy-list", ListView)
        list_view.clear()
        for buddy in buddies:
            list_view.append(ListItem(Label(buddy.screen_name)))


class ConversationList(Static):
    def compose(self) -> ComposeResult:
        yield Label("Chats", classes="panel-title")
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

    def append_message(
        self,
        role: str,
        content: str,
        display_name: str | None = None,
    ) -> Static:
        body = self.query_one("#transcript-body", VerticalScroll)
        label = display_name if display_name is not None else role
        message = Static(f"{label}: {content}", classes=f"message {role}-message")
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
            yield Static("memory empty", id="status-memory")
            yield Static(
                format_usage_status(0, 0, 0.0),
                id="status-usage",
            )

    def set_model(self, provider_id: str, model: str) -> None:
        self.query_one("#status-model", Static).update(f"{provider_id} / {model}")

    def set_memory(self, status: str) -> None:
        self.query_one("#status-memory", Static).update(status)

    def set_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cache_read_input_tokens: int = 0,
        cache_creation_5m_input_tokens: int = 0,
        cache_creation_1h_input_tokens: int = 0,
    ) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cost_usd = cost_usd
        self._cache_read_input_tokens = cache_read_input_tokens
        self._cache_creation_5m_input_tokens = cache_creation_5m_input_tokens
        self._cache_creation_1h_input_tokens = cache_creation_1h_input_tokens
        self._refresh_usage()

    def add_usage(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
        cache_read_input_tokens: int = 0,
        cache_creation_5m_input_tokens: int = 0,
        cache_creation_1h_input_tokens: int = 0,
    ) -> None:
        current_input = getattr(self, "_input_tokens", 0) + (input_tokens or 0)
        current_output = getattr(self, "_output_tokens", 0) + (output_tokens or 0)
        current_cost = getattr(self, "_cost_usd", 0.0) + (cost_usd or 0.0)
        current_cache_read = (
            getattr(self, "_cache_read_input_tokens", 0) + cache_read_input_tokens
        )
        current_cache_creation_5m = (
            getattr(self, "_cache_creation_5m_input_tokens", 0)
            + cache_creation_5m_input_tokens
        )
        current_cache_creation_1h = (
            getattr(self, "_cache_creation_1h_input_tokens", 0)
            + cache_creation_1h_input_tokens
        )
        self._input_tokens = current_input
        self._output_tokens = current_output
        self._cost_usd = current_cost
        self._cache_read_input_tokens = current_cache_read
        self._cache_creation_5m_input_tokens = current_cache_creation_5m
        self._cache_creation_1h_input_tokens = current_cache_creation_1h
        self._refresh_usage()

    def _refresh_usage(self) -> None:
        input_tokens = getattr(self, "_input_tokens", 0)
        output_tokens = getattr(self, "_output_tokens", 0)
        cost_usd = getattr(self, "_cost_usd", 0.0)
        cache_read = getattr(self, "_cache_read_input_tokens", 0)
        cache_creation_5m = getattr(self, "_cache_creation_5m_input_tokens", 0)
        cache_creation_1h = getattr(self, "_cache_creation_1h_input_tokens", 0)
        self.query_one("#status-usage", Static).update(
            format_usage_status(
                input_tokens,
                output_tokens,
                cost_usd,
                cache_read,
                cache_creation_5m,
                cache_creation_1h,
            )
        )
