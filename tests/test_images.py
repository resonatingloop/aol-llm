from dataclasses import fields
import base64

from aol_llm.core.types import Message

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


def test_message_has_immutable_empty_image_default() -> None:
    image_fields = [field for field in fields(Message) if field.name == "images"]
    assert len(image_fields) == 1
    assert image_fields[0].default == ()


def test_png_import_snapshots_bytes_and_detects_mime() -> None:
    from aol_llm.core.images import image_from_bytes

    image = image_from_bytes(PNG, "misleading.jpg")
    assert image.name == "misleading.jpg"
    assert image.media_type == "image/png"
    assert image.data == PNG
