"""Update or check generated documentation blocks."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MarkerRenderer = Callable[[], str]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed = []
    for path in _target_docs():
        original = path.read_text(encoding="utf-8")
        updated = _update_text(original)
        if updated == original:
            continue
        changed.append(path)
        if not args.check:
            path.write_text(updated, encoding="utf-8")

    if args.check and changed:
        for path in changed:
            print(f"generated docs out of date: {path.relative_to(ROOT)}")
        return 1
    return 0


def _target_docs() -> tuple[Path, ...]:
    return (
        ROOT / "README.md",
        ROOT / "CONTRACTS.md",
        ROOT / "docs" / "USER_MANUAL.md",
        ROOT / "docs" / "CODEBASE_SCHEMA.md",
    )


def _update_text(text: str) -> str:
    for marker, renderer in _renderers().items():
        text = _replace_marker(text, marker, renderer())
    return text


def _renderers() -> dict[str, MarkerRenderer]:
    return {
        "provider-defaults-toml": _provider_defaults_toml,
        "provider-defaults-text": _provider_defaults_text,
        "keybindings-table": _keybindings_table,
        "keybindings-text": _keybindings_text,
        "slash-commands-table": _slash_commands_table,
        "slash-commands-list": _slash_commands_list,
    }


def _replace_marker(text: str, marker: str, replacement: str) -> str:
    begin = f"<!-- BEGIN AUTOGEN:{marker} -->"
    end = f"<!-- END AUTOGEN:{marker} -->"
    if begin not in text:
        return text
    before, rest = text.split(begin, 1)
    _, after = rest.split(end, 1)
    return f"{before}{begin}\n{replacement.rstrip()}\n{end}{after}"


def _provider_defaults_toml() -> str:
    from aol_llm.config import default_config

    config = default_config()
    lines = [
        "```toml",
        "[ui]",
        f'theme = "{config.ui.theme}"',
        f'default_provider = "{config.ui.default_provider}"',
        f'assistant_name = "{config.ui.assistant_name}"',
        "",
        "[memory]",
        f'distiller_provider = "{config.memory.distiller_provider}"',
        f'distiller_model = "{config.memory.distiller_model}"',
        "",
    ]
    for provider_id, settings in config.providers.items():
        lines.append(f"[providers.{provider_id}]")
        if settings.base_url is not None:
            lines.append(f'base_url = "{settings.base_url}"')
        lines.append(f'default_model = "{settings.default_model}"')
        lines.append("")
    lines[-1] = "```"
    return "\n".join(lines)


def _provider_defaults_text() -> str:
    from aol_llm.config import default_config

    lines = []
    for provider_id, settings in default_config().providers.items():
        base_url = "" if settings.base_url is None else f"  {settings.base_url}"
        lines.append(
            f"{provider_id:<10} {settings.default_model:<24}{base_url}".rstrip()
        )
    return "\n".join(lines)


def _keybindings_table() -> str:
    lines = ["| Key | Action |", "| --- | --- |"]
    for key, description in _binding_rows():
        lines.append(f"| `{key}` | {description} |")
    return "\n".join(lines)


def _keybindings_text() -> str:
    width = max(len(key) for key, _ in _binding_rows())
    return "\n".join(
        f"{key:<{width}}   {description}" for key, description in _binding_rows()
    )


def _slash_commands_table() -> str:
    from aol_llm.ui.commands import SLASH_COMMAND_DOCS

    lines = ["| Command | Action |", "| --- | --- |"]
    for command in SLASH_COMMAND_DOCS:
        lines.append(f"| `{command.command}` | {command.action} |")
    return "\n".join(lines)


def _slash_commands_list() -> str:
    from aol_llm.ui.commands import SLASH_COMMAND_DOCS

    return "\n".join(f"- `{command.command}`" for command in SLASH_COMMAND_DOCS)


def _binding_rows() -> list[tuple[str, str]]:
    from textual.binding import Binding

    from aol_llm.ui.styles import APP_BINDINGS

    return [
        (binding.key, binding.description)
        for binding in APP_BINDINGS
        if isinstance(binding, Binding)
    ]


if __name__ == "__main__":
    raise SystemExit(main())
