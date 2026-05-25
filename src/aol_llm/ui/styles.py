"""Textual styling constants."""

from textual.binding import Binding

APP_CSS = """
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

APP_BINDINGS: list[Binding | tuple[str, str] | tuple[str, str, str]] = [
    ("ctrl+n", "new_conversation", "New"),
    ("ctrl+enter", "send_message", "Send"),
    ("ctrl+t", "rename_current_chat", "Rename"),
    ("ctrl+p", "edit_system_prompt", "System"),
    ("ctrl+m", "open_model_picker", "Model"),
    ("f2", "open_settings", "Settings"),
    ("ctrl+r", "retry_last", "Retry"),
    ("ctrl+e", "export_current_chat", "Export"),
    ("ctrl+x", "archive_current_chat", "Archive"),
    ("ctrl+d", "delete_current_chat", "Delete"),
    ("ctrl+q", "quit", "Quit"),
]
