"""Slash command parsing for composer input."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: tuple[str, ...]


def parse_slash_command(text: str) -> SlashCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped[1:].split()
    if not parts:
        return SlashCommand(name="", args=())
    return SlashCommand(name=parts[0].lower(), args=tuple(parts[1:]))
