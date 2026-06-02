"""Conversation export helpers."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re

from aol_llm.core.types import Conversation, Message


def export_markdown(
    conversation: Conversation,
    messages: list[Message],
    reply_name: str | None = None,
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
    content = (
        export_markdown(conversation, messages, reply_name=reply_name)
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
    return data


def _usage_line(message: Message) -> str | None:
    if message.input_tokens is None and message.output_tokens is None:
        return None
    cost = "" if message.cost_usd is None else f", cost ${message.cost_usd:.6f}"
    return (
        f"_Usage: input {message.input_tokens or 0}, "
        f"output {message.output_tokens or 0}{cost}_"
    )


def _extension(format: str) -> str:
    if format == "markdown":
        return "md"
    if format == "json":
        return "json"
    raise ValueError(f"unknown export format: {format}")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "conversation"
