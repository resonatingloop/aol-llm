from aol_llm.ui.commands import (
    SLASH_COMMAND_DOCS,
    SlashCommand,
    parse_slash_command,
    slash_command_detail_summary,
    slash_command_help_summary,
)
from aol_llm.ui.widgets import format_usage_status


def test_parse_slash_command_returns_none_for_regular_messages() -> None:
    assert parse_slash_command("hello /cache on") is None


def test_parse_slash_command_normalizes_name_and_args() -> None:
    assert parse_slash_command("  /CACHE on  ") == SlashCommand(
        name="cache",
        args=("on",),
    )


def test_parse_slash_command_keeps_memory_subcommand_as_arg() -> None:
    assert parse_slash_command("/memory refactor") == SlashCommand(
        name="memory",
        args=("refactor",),
    )


def test_parse_slash_command_handles_empty_slash() -> None:
    assert parse_slash_command("/") == SlashCommand(name="", args=())


def test_slash_command_help_summary_lists_documented_commands() -> None:
    summary = slash_command_help_summary()

    assert "/help" not in summary
    for command in SLASH_COMMAND_DOCS:
        if command.command != "/help":
            assert command.command in summary


def test_slash_command_detail_summary_includes_actions() -> None:
    summary = slash_command_detail_summary()

    assert "/help" not in summary
    assert "/memory status" in summary
    assert "Show active buddy memory status" in summary


def test_format_usage_status_includes_cache_counters() -> None:
    assert (
        format_usage_status(
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.12345,
            cache_read_input_tokens=30,
            cache_creation_5m_input_tokens=40,
            cache_creation_1h_input_tokens=50,
        )
        == "input 10 / output 20 / cache r 30 w5 40 w1h 50 / $0.1235"
    )
