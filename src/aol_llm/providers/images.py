"""Provider-native content blocks for image-bearing user messages."""

import base64

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.images import validate_images
from aol_llm.core.types import Message


def anthropic_content(message: Message) -> str | list[dict[str, object]]:
    if not message.images:
        return message.content
    blocks: list[dict[str, object]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            },
        }
        for media_type, data in _encoded_images(message)
    ]
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    return blocks


def openai_chat_content(message: Message) -> str | list[dict[str, object]]:
    if not message.images:
        return message.content
    blocks: list[dict[str, object]] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{data}"},
        }
        for media_type, data in _encoded_images(message)
    ]
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    return blocks


def openai_response_content(message: Message) -> str | list[dict[str, object]]:
    if not message.images:
        return message.content
    blocks: list[dict[str, object]] = [
        {
            "type": "input_image",
            "image_url": f"data:{media_type};base64,{data}",
        }
        for media_type, data in _encoded_images(message)
    ]
    if message.content:
        blocks.append({"type": "input_text", "text": message.content})
    return blocks


def _encoded_images(message: Message) -> list[tuple[str, str]]:
    if message.role != "user":
        raise UnknownProviderError("Images are supported only on user messages")
    try:
        validate_images(message.images)
    except ValueError as error:
        raise UnknownProviderError(f"Invalid images: {error}") from error
    return [
        (image.media_type, base64.b64encode(image.data).decode("ascii"))
        for image in message.images
    ]
