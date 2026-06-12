from aol_llm.ui.commands import SlashCommand, parse_slash_command


def test_parse_slash_command_returns_none_for_regular_messages() -> None:
    assert parse_slash_command("hello /cache on") is None


def test_parse_slash_command_normalizes_name_and_args() -> None:
    assert parse_slash_command("  /CACHE on  ") == SlashCommand(
        name="cache",
        args=("on",),
    )


def test_parse_slash_command_handles_empty_slash() -> None:
    assert parse_slash_command("/") == SlashCommand(name="", args=())
