"""Slash command parsing for composer input."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommandDoc:
    command: str
    action: str


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: tuple[str, ...]


SLASH_COMMAND_DOCS: tuple[SlashCommandDoc, ...] = (
    SlashCommandDoc("/cache on", "Enable one-hour Claude prompt caching"),
    SlashCommandDoc("/cache 1h", "Enable one-hour Claude prompt caching"),
    SlashCommandDoc("/cache 5m", "Enable five-minute Claude prompt caching"),
    SlashCommandDoc("/cache off", "Disable Claude prompt caching"),
    SlashCommandDoc("/cache status", "Show whether Claude prompt caching is enabled"),
    SlashCommandDoc("/help", "Show the current command summary"),
    SlashCommandDoc(
        "/copy",
        "Copy last prompt + response pair in active chat to clipboard",
    ),
    SlashCommandDoc("/export", "Open export menu"),
    SlashCommandDoc("/away", "Open a-way menu"),
    SlashCommandDoc("/buddy", "Open active buddy picker"),
    SlashCommandDoc("/chatname", "Open current chat name editor"),
    SlashCommandDoc("/quit", "Quit"),
    SlashCommandDoc("/settings", "Open settings"),
)


def slash_command_help_summary() -> str:
    commands = [doc.command for doc in SLASH_COMMAND_DOCS if doc.command != "/help"]
    return "Commands: " + ", ".join(commands)


def parse_slash_command(text: str) -> SlashCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped[1:].split()
    if not parts:
        return SlashCommand(name="", args=())
    return SlashCommand(name=parts[0].lower(), args=tuple(parts[1:]))
