"""Conversation export helpers."""

from __future__ import annotations

import base64
from dataclasses import asdict
import json
from pathlib import Path
import re

from aol_llm.core.images import image_summary
from aol_llm.core.types import Conversation, ImageAttachment, Message


def export_markdown(
    conversation: Conversation,
    messages: list[Message],
    reply_name: str | None = None,
    image_directory: str | None = None,
) -> str:
    lines = [
        f"# {conversation.title}",
        "",
        f"- Provider: `{conversation.provider_id}`",
        f"- Model: `{conversation.model}`",
        f"- Created: `{conversation.created_at.isoformat()}`",
        f"- Updated: `{conversation.updated_at.isoformat()}`",
    ]
    if conversation.system_prompt:
        lines.extend(["", "## a-way", "", conversation.system_prompt])

    lines.extend(["", "## Messages", ""])
    for message in messages:
        label = (
            reply_name if message.role == "assistant" and reply_name else message.role
        )
        lines.extend(
            [
                f"### {label.title()}",
                "",
                message.content,
                "",
            ]
        )
        if message.images:
            if image_directory is None:
                lines.extend([image_summary(message.images), ""])
            else:
                for index, image in enumerate(message.images):
                    label = image.name.replace("[", "\\[").replace("]", "\\]")
                    lines.extend(
                        [
                            f"![{label}]({image_directory}/{_image_filename(message, index, image)})",
                            "",
                        ]
                    )
        usage = _usage_line(message)
        if usage is not None:
            lines.extend([usage, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_json(
    conversation: Conversation,
    messages: list[Message],
    reply_name: str | None = None,
) -> str:
    payload = {
        "conversation": _json_dataclass(conversation),
        "messages": [_json_dataclass(message) for message in messages],
    }
    if reply_name is not None:
        payload["reply_name"] = reply_name
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def export_last_pair_markdown(
    messages: list[Message],
    reply_name: str | None = None,
) -> str | None:
    pair = _last_user_assistant_pair(messages)
    if pair is None:
        return None

    user_message, assistant_message = pair
    assistant_label = reply_name or assistant_message.role
    return "\n".join(
        [
            "### User",
            "",
            "\n".join(
                filter(None, [user_message.content, image_summary(user_message.images)])
            ),
            "",
            f"### {assistant_label.title()}",
            "",
            assistant_message.content,
            "",
        ]
    )


def write_export(
    conversation: Conversation,
    messages: list[Message],
    directory: Path,
    format: str,
    reply_name: str | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    extension = _extension(format)
    path = directory / f"{_slug(conversation.title)}-{conversation.id}.{extension}"
    image_directory = None
    if format == "markdown" and any(message.images for message in messages):
        image_directory = f"{path.stem}-images"
        folder = directory / image_directory
        folder.mkdir(parents=True, exist_ok=True)
        for message in messages:
            for index, image in enumerate(message.images):
                (folder / _image_filename(message, index, image)).write_bytes(
                    image.data
                )
    content = (
        export_markdown(
            conversation,
            messages,
            reply_name=reply_name,
            image_directory=image_directory,
        )
        if format == "markdown"
        else export_json(conversation, messages, reply_name=reply_name)
    )
    path.write_text(content, encoding="utf-8")
    return path


def _json_dataclass(value: Conversation | Message) -> dict[str, object]:
    data = asdict(value)
    data["created_at"] = value.created_at.isoformat()
    if isinstance(value, Conversation):
        data["updated_at"] = value.updated_at.isoformat()
    elif value.images:
        data["images"] = [
            {
                "name": image.name,
                "media_type": image.media_type,
                "data_base64": base64.b64encode(image.data).decode("ascii"),
            }
            for image in value.images
        ]
    else:
        data.pop("images", None)
    return data


def _image_filename(message: Message, index: int, image: ImageAttachment) -> str:
    extension = (
        "jpg"
        if image.media_type == "image/jpeg"
        else image.media_type.removeprefix("image/")
    )
    return f"{_slug(message.id)}-{index}.{extension}"


def _usage_line(message: Message) -> str | None:
    if message.input_tokens is None and message.output_tokens is None:
        return None
    cost = "" if message.cost_usd is None else f", cost ${message.cost_usd:.6f}"
    return (
        f"_Usage: input {message.input_tokens or 0}, "
        f"output {message.output_tokens or 0}{cost}_"
    )


def _last_user_assistant_pair(
    messages: list[Message],
) -> tuple[Message, Message] | None:
    for index in range(len(messages) - 1, 0, -1):
        assistant_message = messages[index]
        user_message = messages[index - 1]
        if assistant_message.role == "assistant" and user_message.role == "user":
            return user_message, assistant_message
    return None


def _extension(format: str) -> str:
    if format == "markdown":
        return "md"
    if format == "json":
        return "json"
    raise ValueError(f"unknown export format: {format}")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "conversation"
