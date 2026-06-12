from datetime import UTC, datetime
import json

from aol_llm.core.types import Conversation, Message
from aol_llm.export import export_json, export_last_pair_markdown, export_markdown


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
    content = export_markdown(conversation(), messages(), reply_name="Threshold")

    assert "# Example Chat" in content
    assert "## a-way\n\nBe concise." in content
    assert "### User\n\nhello" in content
    assert "### Threshold\n\nhi" in content
    assert "_Usage: input 1, output 2, cost $0.000010_" in content


def test_export_json_serializes_conversation_and_messages() -> None:
    payload = json.loads(
        export_json(conversation(), messages(), reply_name="Threshold")
    )

    assert payload["conversation"]["system_prompt"] == "Be concise."
    assert payload["reply_name"] == "Threshold"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["cost_usd"] == 0.00001


def test_export_last_pair_markdown_copies_final_prompt_and_response() -> None:
    now = datetime(2026, 5, 25, tzinfo=UTC)
    source = messages() + [
        Message(
            id="msg3",
            conversation_id="chat1",
            role="user",
            content="next",
            created_at=now,
        ),
        Message(
            id="msg4",
            conversation_id="chat1",
            role="assistant",
            content="reply",
            created_at=now,
        ),
    ]

    assert export_last_pair_markdown(source, reply_name="Threshold") == (
        "### User\n\nnext\n\n### Threshold\n\nreply\n"
    )


def test_export_last_pair_markdown_requires_complete_pair() -> None:
    assert export_last_pair_markdown(messages()[:1]) is None
