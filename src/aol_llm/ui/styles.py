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

#buddy-pane {
    height: 1fr;
}

#chat-list-pane {
    height: 1fr;
    border-top: solid $panel;
    padding-top: 1;
}

#buddy-list {
    height: 1fr;
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
    Binding("f1", "open_settings", "Settings", priority=True),
    Binding("f2", "open_model_picker", "Model", priority=True),
    Binding("f3", "edit_system_prompt", "a-way", priority=True),
    Binding("f4", "rename_current_buddy", "Rename buddy", priority=True),
    Binding("f5", "send_message", "Send", priority=True),
    Binding("f6", "new_conversation", "New", priority=True),
    Binding("f7", "retry_last", "Retry", priority=True),
    Binding("f8", "rename_current_chat", "Rename chat", priority=True),
    Binding("f9", "export_current_chat", "Export", priority=True),
    Binding("ctrl+shift+c", "copy_current_chat", "Copy", priority=True),
    Binding("ctrl+x", "archive_current_chat", "Archive", priority=True),
    Binding("ctrl+d", "delete_current_chat", "Delete", priority=True),
    Binding("ctrl+c", "quit", "Quit", priority=True),
]
