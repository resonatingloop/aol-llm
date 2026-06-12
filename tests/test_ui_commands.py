from aol_llm.ui.commands import SlashCommand, parse_slash_command
from aol_llm.ui.widgets import format_usage_status


def test_parse_slash_command_returns_none_for_regular_messages() -> None:
    assert parse_slash_command("hello /cache on") is None


def test_parse_slash_command_normalizes_name_and_args() -> None:
    assert parse_slash_command("  /CACHE on  ") == SlashCommand(
        name="cache",
        args=("on",),
    )


def test_parse_slash_command_handles_empty_slash() -> None:
    assert parse_slash_command("/") == SlashCommand(name="", args=())


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
