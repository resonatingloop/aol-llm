from datetime import UTC, datetime
import json

from aol_llm.core.types import Conversation, Message
from aol_llm.export import export_json, export_markdown


def conversation() -> Conversation:
    now = datetime(2026, 5, 25, tzinfo=UTC)
    return Conversation(
        id="chat1",
        title="Example Chat",
        system_prompt="Be concise.",
        provider_id="anthropic",
        model="claude-test",
        created_at=now,
        updated_at=now,
    )


def messages() -> list[Message]:
    now = datetime(2026, 5, 25, tzinfo=UTC)
    return [
        Message(
            id="msg1",
            conversation_id="chat1",
            role="user",
            content="hello",
            created_at=now,
        ),
        Message(
            id="msg2",
            conversation_id="chat1",
            role="assistant",
            content="hi",
            created_at=now,
            model="claude-test",
            input_tokens=1,
            output_tokens=2,
            cost_usd=0.00001,
        ),
    ]


def test_export_markdown_includes_system_messages_and_usage() -> None:
    content = export_markdown(conversation(), messages())

    assert "# Example Chat" in content
    assert "## System Prompt\n\nBe concise." in content
    assert "### User\n\nhello" in content
    assert "_Usage: input 1, output 2, cost $0.000010_" in content


def test_export_json_serializes_conversation_and_messages() -> None:
    payload = json.loads(export_json(conversation(), messages()))

    assert payload["conversation"]["system_prompt"] == "Be concise."
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["cost_usd"] == 0.00001
