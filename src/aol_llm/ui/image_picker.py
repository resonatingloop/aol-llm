"""Image file selection in the terminal UI."""

from collections.abc import Iterable
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Label

from aol_llm.core.images import IMAGE_EXTENSIONS


class ImageFileTree(DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [
            path
            for path in paths
            if path.is_dir() or path.suffix.lower() in IMAGE_EXTENSIONS
        ]


class ImagePickerModal(ModalScreen[Path | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    ImagePickerModal { align: center middle; }
    #image-picker-modal {
        width: 80; height: 85%; border: solid $accent;
        background: $surface; padding: 1 2;
    }
    #image-file-tree { height: 1fr; margin: 1 0; }
    #image-picker-error { height: auto; color: $error; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="image-picker-modal"):
            yield Label("Choose image: PNG, JPEG, GIF, WebP (up to 5 MiB)")
            yield ImageFileTree(Path.home(), id="image-file-tree")
            yield Input(placeholder="Or enter a full image path", id="image-file-path")
            yield Label("", id="image-picker-error")
            with Horizontal(classes="modal-actions"):
                yield Button("Cancel", id="cancel-image-picker")
                yield Button("Attach image", id="select-image-file", variant="primary")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.query_one("#image-file-path", Input).value = str(event.path)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._select_file()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-image-file":
            self._select_file()
        elif event.button.id == "cancel-image-picker":
            self.dismiss(None)

    def _select_file(self) -> None:
        value = self.query_one("#image-file-path", Input).value
        if not value.strip():
            self.query_one("#image-picker-error", Label).update("Select an image first")
            return
        path = Path(value).expanduser()
        if not path.is_file():
            self.query_one("#image-picker-error", Label).update(
                "Choose an existing file"
            )
            return
        self.dismiss(path)

    def action_cancel(self) -> None:
        self.dismiss(None)
