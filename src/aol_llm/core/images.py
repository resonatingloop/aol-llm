"""Provider-neutral local image snapshots and bounded validation."""

from pathlib import Path

from aol_llm.core.types import ImageAttachment

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 10
MAX_MESSAGE_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


def image_from_bytes(data: bytes, name: str) -> ImageAttachment:
    """Detect the image format from bytes, not a potentially misleading suffix."""
    if not data:
        raise ValueError("Image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 5 MiB limit")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        media_type = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        media_type = "image/webp"
    else:
        raise ValueError("Unsupported image; choose PNG, JPEG, GIF, or WebP")
    clean_name = Path(name).name
    clean_name = "".join(
        character for character in clean_name if character.isprintable()
    )
    if not clean_name or clean_name in {".", ".."}:
        clean_name = "image." + media_type.removeprefix("image/")
    return ImageAttachment(name=clean_name, media_type=media_type, data=data)


def read_image(path: Path) -> ImageAttachment:
    """Snapshot a regular file, with a bounded read even if it changes size."""
    path = path.expanduser()
    if not path.is_file():
        raise ValueError("Choose an existing image file")
    with path.open("rb") as source:
        data = source.read(MAX_IMAGE_BYTES + 1)
    return image_from_bytes(data, path.name)


def validate_images(images: tuple[ImageAttachment, ...]) -> None:
    if len(images) > MAX_IMAGES:
        raise ValueError("At most 10 images can be attached to one message")
    if sum(len(image.data) for image in images) > MAX_MESSAGE_IMAGE_BYTES:
        raise ValueError("Message images exceed the 20 MiB total limit")
    for image in images:
        detected = image_from_bytes(image.data, image.name)
        if detected.media_type != image.media_type:
            raise ValueError("Image media type does not match its bytes")


def image_summary(images: tuple[ImageAttachment, ...]) -> str:
    """Text-only transcript/copy annotation; never include image bytes."""
    return "\n".join(f"[Image: {image.name}]" for image in images)
