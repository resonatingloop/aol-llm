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

#status-memory {
    width: auto;
    padding: 0 2;
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
    Binding("f2", "rename_current_buddy", "Rename buddy", priority=True),
    Binding("f3", "send_message", "Send message", priority=True),
    Binding("f4", "new_conversation", "New chat", priority=True),
    Binding("f5", "archive_current_chat", "Archive chat", priority=True),
    Binding("f6", "delete_current_chat", "Delete chat", priority=True),
    Binding("f7", "retry_last", "Retry", priority=True),
    Binding("ctrl+c", "quit", "Quit", priority=True),
]
