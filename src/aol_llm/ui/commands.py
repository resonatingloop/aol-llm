"""Slash command parsing for composer input."""

from collections.abc import Callable
from dataclasses import dataclass

from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.widgets import TextArea


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
    SlashCommandDoc("/memory status", "Show active buddy memory status"),
    SlashCommandDoc("/memory on", "Enable active buddy memory injection"),
    SlashCommandDoc("/memory off", "Disable active buddy memory injection"),
    SlashCommandDoc("/memory forget", "Forget active buddy memory"),
    SlashCommandDoc("/memory distill", "Distill memory for the active buddy"),
    SlashCommandDoc("/memory refactor", "Refactor memory for the active buddy"),
    SlashCommandDoc("/buddy", "Open active buddy picker"),
    SlashCommandDoc("/chatname", "Open current chat name editor"),
    SlashCommandDoc("/quit", "Quit"),
    SlashCommandDoc("/settings", "Open settings"),
)


def slash_command_help_summary() -> str:
    commands = [doc.command for doc in SLASH_COMMAND_DOCS if doc.command != "/help"]
    return "Commands: " + ", ".join(commands)


def slash_command_detail_summary() -> str:
    return "\n".join(
        f"{doc.command:<16} {doc.action}"
        for doc in SLASH_COMMAND_DOCS
        if doc.command != "/help"
    )


def parse_slash_command(text: str) -> SlashCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped[1:].split()
    if not parts:
        return SlashCommand(name="", args=())
    return SlashCommand(name=parts[0].lower(), args=tuple(parts[1:]))


class SlashCommandProvider(Provider):
    """Command palette provider for composer slash commands."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for doc in SLASH_COMMAND_DOCS:
            if doc.command == "/help":
                continue
            candidate = f"{doc.command} {doc.action}"
            if (score := matcher.match(candidate)) > 0:
                yield Hit(
                    score,
                    matcher.highlight(f"Slash Commands: {doc.command}"),
                    self._insert_command(doc.command),
                    text=doc.command,
                    help=doc.action,
                )

    async def discover(self) -> Hits:
        for doc in SLASH_COMMAND_DOCS:
            if doc.command == "/help":
                continue
            yield DiscoveryHit(
                f"Slash Commands: {doc.command}",
                self._insert_command(doc.command),
                text=doc.command,
                help=doc.action,
            )

    def _insert_command(self, command: str) -> Callable[[], None]:
        def insert_command() -> None:
            composer = self.app.query_one("#composer-input", TextArea)
            composer.text = command
            composer.focus()

        return insert_command
