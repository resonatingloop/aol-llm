"""Textual modals for the AOL-LLM shell."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView


class ModelPickerModal(ModalScreen[str | None]):
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

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker"):
            yield Label("Model")
            yield ListView(
                ListItem(Label("claude-sonnet-test")),
                ListItem(Label("gpt-test")),
                id="model-options",
            )
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-model")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-model":
            self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
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
