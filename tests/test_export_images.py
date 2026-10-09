import base64
from datetime import UTC, datetime
import json
from pathlib import Path

from aol_llm.core.images import image_from_bytes
from aol_llm.core.types import Conversation, Message
from aol_llm.export import export_json, export_last_pair_markdown, write_export

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


def fixtures() -> tuple[Conversation, list[Message]]:
    now = datetime.now(UTC)
    chat = Conversation("chat", "Images", None, "openai", "test", now, now)
    messages = [
        Message(
            "user-id",
            "chat",
            "user",
            "Look",
            now,
            images=(image_from_bytes(PNG, "pixel.png"),),
        ),
        Message("assistant-id", "chat", "assistant", "A pixel", now),
    ]
    return chat, messages


def test_json_export_contains_self_contained_image_bytes() -> None:
    chat, messages = fixtures()
    payload = json.loads(export_json(chat, messages))
    image = payload["messages"][0]["images"][0]
    assert image["name"] == "pixel.png"
    assert image["media_type"] == "image/png"
    assert base64.b64decode(image["data_base64"]) == PNG


def test_markdown_export_writes_linked_image_snapshots(tmp_path: Path) -> None:
    chat, messages = fixtures()
    path = write_export(chat, messages, tmp_path, "markdown")
    expected = tmp_path / "images-chat-images" / "user-id-0.png"
    assert expected.read_bytes() == PNG
    assert "![pixel.png](images-chat-images/user-id-0.png)" in path.read_text()
    copied = export_last_pair_markdown(messages)
    assert copied is not None
    assert "[Image: pixel.png]" in copied
    assert "data:image" not in copied
