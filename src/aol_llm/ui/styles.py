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
    height: 1fr;
    border-right: solid $panel;
    padding: 1;
}

#conversation-list {
    height: 1fr;
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
    Binding("ctrl+n", "new_conversation", "New", priority=True),
    Binding("f5", "send_message", "Send", priority=True),
    Binding("ctrl+t", "rename_current_chat", "Rename", priority=True),
    Binding("f3", "edit_system_prompt", "System", priority=True),
    Binding("f4", "open_model_picker", "Model", priority=True),
    Binding("f2", "open_settings", "Settings", priority=True),
    Binding("ctrl+r", "retry_last", "Retry", priority=True),
    Binding("ctrl+e", "export_current_chat", "Export", priority=True),
    Binding("ctrl+x", "archive_current_chat", "Archive", priority=True),
    Binding("ctrl+d", "delete_current_chat", "Delete", priority=True),
    Binding("ctrl+q", "quit", "Quit", priority=True),
]
