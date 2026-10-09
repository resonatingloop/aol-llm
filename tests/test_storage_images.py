import base64
from pathlib import Path
import sqlite3

import pytest

from aol_llm.core.images import image_from_bytes, read_image
from aol_llm.storage import db

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


def test_images_round_trip_after_source_is_deleted(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    db.init_db(path)
    chat = db.create_conversation("Images", "anthropic", "test", path=path)
    source = tmp_path / "first.png"
    source.write_bytes(PNG)
    first = read_image(source)
    second = image_from_bytes(PNG, "second.png")
    sent = db.add_message(chat.id, "user", "Look", path=path, images=(first, second))
    source.unlink()
    reopened = db.list_messages(chat.id, path)
    assert reopened == [sent]
    assert reopened[0].images == (first, second)
    db.init_db(path)
    assert db.list_messages(chat.id, path)[0].images == (first, second)


@pytest.mark.parametrize("delete_chat", [False, True])
def test_image_rows_cascade_on_delete(tmp_path: Path, delete_chat: bool) -> None:
    path = tmp_path / "chat.db"
    db.init_db(path)
    chat = db.create_conversation("Images", "anthropic", "test", path=path)
    message = db.add_message(
        chat.id,
        "user",
        "",
        path=path,
        images=(image_from_bytes(PNG, "pixel.png"),),
    )
    if delete_chat:
        db.delete_conversation(chat.id, path)
    else:
        db.delete_message(message.id, path)
    with db.get_connection(path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM message_images").fetchone()[0] == 0
        )


def test_image_insert_failure_rolls_back_entire_message(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    db.init_db(path)
    chat = db.create_conversation("Images", "anthropic", "test", path=path)
    with db.get_connection(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_image BEFORE INSERT ON message_images "
            "WHEN NEW.position = 1 BEGIN SELECT RAISE(ABORT, 'image failure'); END"
        )
    image = image_from_bytes(PNG, "pixel.png")
    with pytest.raises(sqlite3.IntegrityError, match="image failure"):
        db.add_message(chat.id, "user", "Look", path=path, images=(image, image))
    assert db.list_messages(chat.id, path) == []
    with db.get_connection(path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM message_images").fetchone()[0] == 0
        )


def test_upgrade_preserves_text_history_and_memory(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    db.init_db(path)
    chat = db.create_conversation("Before upgrade", "anthropic", "test", path=path)
    text = db.add_message(chat.id, "user", "Existing history", path=path)
    buddy = db.ensure_buddy("anthropic", "test", path)
    memory = db.upsert_buddy_memory(buddy.id, "Retained memory", path=path)
    with db.get_connection(path) as connection:
        # Restore the actual pre-image schema, retaining all historical data.
        connection.execute("DROP TABLE message_images")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = '009_message_images'"
        )
    db.init_db(path)
    db.init_db(path)
    assert db.list_messages(chat.id, path) == [text]
    assert db.get_buddy_memory(buddy.id, path) == memory
