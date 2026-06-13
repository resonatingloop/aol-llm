"""Textual modals for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, TextArea

from aol_llm.chat import ModelChoice
from aol_llm.core.types import Buddy


class ModelPickerModal(ModalScreen[ModelChoice | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ModelPickerModal {
        align: center middle;
    }

    #model-picker {
        width: 52;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, choices: list[ModelChoice]) -> None:
        super().__init__()
        self._choices = choices

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker"):
            yield Label("Model")
            yield ListView(
                *[
                    ListItem(Label(f"{choice.provider_id} / {choice.model}"))
                    for choice in self._choices
                ],
                id="model-options",
            )
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-model")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "model-options":
            return
        self.dismiss(self._choices[event.index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-model":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class BuddyPickerModal(ModalScreen[Buddy | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    BuddyPickerModal {
        align: center middle;
    }

    #buddy-picker {
        width: 52;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, buddies: list[Buddy]) -> None:
        super().__init__()
        self._buddies = buddies

    def compose(self) -> ComposeResult:
        with Vertical(id="buddy-picker"):
            yield Label("Buddy")
            yield ListView(
                *[
                    ListItem(Label(f"{buddy.screen_name} / {buddy.model}"))
                    for buddy in self._buddies
                ],
                id="buddy-options",
            )
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-buddy")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "buddy-options":
            return
        self.dismiss(self._buddies[event.index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-buddy":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class RenameModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    RenameModal {
        align: center middle;
    }

    #rename-modal {
        width: 52;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, current_title: str, label: str = "Rename chat") -> None:
        super().__init__()
        self._current_title = current_title
        self._label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="rename-modal"):
            yield Label(self._label)
            yield Input(value=self._current_title, id="rename-input")
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-rename")
                yield Button("Rename", id="confirm-rename", variant="primary")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-rename":
            self.dismiss(None)
            return
        if event.button.id == "confirm-rename":
            self.dismiss(self.query_one("#rename-input", Input).value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SystemPromptModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    SystemPromptModal {
        align: center middle;
    }

    #system-prompt-modal {
        width: 72;
        height: 24;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #system-prompt-input {
        height: 1fr;
    }
    """

    def __init__(self, current_prompt: str | None) -> None:
        super().__init__()
        self._current_prompt = current_prompt or ""

    def compose(self) -> ComposeResult:
        with Vertical(id="system-prompt-modal"):
            yield Label("a-way")
            yield Label(
                "Changing a-way mid-conversation changes the cached prefix; "
                "Claude will write a fresh cache for future sends.",
            )
            yield TextArea(text=self._current_prompt, id="system-prompt-input")
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-system-prompt")
                yield Button("Save", id="save-system-prompt", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-system-prompt":
            self.dismiss(None)
            return
        if event.button.id == "save-system-prompt":
            self.dismiss(self.query_one("#system-prompt-input", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ExportFormatModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ExportFormatModal {
        align: center middle;
    }

    #export-modal {
        width: 44;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="export-modal"):
            yield Label("Export")
            with Horizontal(classes="modal-actions"):
                yield Button("Markdown", id="export-markdown", variant="primary")
                yield Button("JSON", id="export-json")
                yield Button("Cancel", id="cancel-export")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-markdown":
            self.dismiss("markdown")
        elif event.button.id == "export-json":
            self.dismiss("json")
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }

    #confirm-modal {
        width: 48;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-modal"):
            yield Label(self._prompt)
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-confirm")
                yield Button("Confirm", id="confirm-action", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-action")

    def action_cancel(self) -> None:
        self.dismiss(False)
