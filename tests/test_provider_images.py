"""Mocked wire-contract tests for image-bearing provider messages."""

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

import httpx
import pytest
import respx

from aol_llm.core.errors import UnknownProviderError
from aol_llm.core.images import MAX_IMAGE_BYTES, MAX_IMAGES, MAX_MESSAGE_IMAGE_BYTES
from aol_llm.core.types import ImageAttachment, Message, ProviderConfig, Role
from aol_llm.providers.anthropic import ANTHROPIC_MESSAGES_URL, AnthropicProvider
from aol_llm.providers.base import Provider
from aol_llm.providers.openai_compat import OpenAICompatibleProvider
from aol_llm.providers.openai_responses import OpenAIResponseOptions

Api = Literal["anthropic", "compatible", "openai_chat", "responses"]


def images() -> tuple[ImageAttachment, ...]:
    return (
        ImageAttachment(
            name="first.png",
            media_type="image/png",
            data=base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                "AAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII="
            ),
        ),
        ImageAttachment(
            name="second.gif",
            media_type="image/gif",
            data=base64.b64decode(
                "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
            ),
        ),
    )


def message(
    content: str,
    attachments: tuple[ImageAttachment, ...] = (),
    role: Role = "user",
) -> Message:
    return Message(
        id="message-id",
        conversation_id="conversation-id",
        role=role,
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        images=attachments,
    )


def provider(api: Api) -> tuple[Provider, str]:
    base_url = (
        "https://api.compatible.test/v1"
        if api == "compatible"
        else "https://api.openai.com/v1"
    )
    config = ProviderConfig(
        id="test-provider",
        kind="anthropic" if api == "anthropic" else "openai_compatible",
        display_name="Test provider",
        base_url=None if api == "anthropic" else base_url,
        keyring_service=None,
        default_model="unknown-model",
        available_models=[],
    )
    if api == "anthropic":
        return AnthropicProvider(config, "test-key"), ANTHROPIC_MESSAGES_URL
    options = OpenAIResponseOptions() if api == "responses" else None
    endpoint = "responses" if api == "responses" else "chat/completions"
    return (
        OpenAICompatibleProvider(config, "test-key", response_options=options),
        f"{base_url}/{endpoint}",
    )


def response(api: Api) -> httpx.Response:
    if api == "anthropic":
        events = [
            {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
            {"type": "message_delta", "usage": {"output_tokens": 2}},
            {"type": "message_stop"},
        ]
    elif api == "responses":
        events = [
            {
                "type": "response.completed",
                "response": {"usage": {"input_tokens": 7, "output_tokens": 2}},
            }
        ]
    else:
        events = [
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}
        ]
    return httpx.Response(
        200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events)
    )


async def capture(
    api: Api,
    messages: list[Message],
    adapter: Provider | None = None,
) -> dict[str, object]:
    default_adapter, url = provider(api)
    adapter = adapter or default_adapter
    original_messages = list(messages)
    original_content = [(item.content, item.images) for item in messages]
    with respx.mock as router:
        route = router.post(url).mock(return_value=response(api))
        chunks = [
            chunk
            async for chunk in adapter.stream(
                messages, "System prompt", "unknown-model"
            )
        ]
        assert chunks[-1].done and chunks[-1].usage is not None
        payload: dict[str, object] = json.loads(route.calls.last.request.content)
    assert messages == original_messages
    assert [(item.content, item.images) for item in messages] == original_content
    assert all(
        left is right for left, right in zip(messages, original_messages, strict=True)
    )
    return payload


def image_blocks(api: Api) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for image in images():
        data = base64.b64encode(image.data).decode("ascii")
        uri = f"data:{image.media_type};base64,{data}"
        if api == "anthropic":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": data,
                    },
                }
            )
        elif api == "responses":
            blocks.append({"type": "input_image", "image_url": uri})
        else:
            blocks.append({"type": "image_url", "image_url": {"url": uri}})
    return blocks


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["anthropic", "compatible", "openai_chat", "responses"])
@pytest.mark.parametrize("text", ["Describe these images", ""])
async def test_serializes_multiple_images_in_order(api: Api, text: str) -> None:
    payload = await capture(api, [message(text, images())])
    blocks = image_blocks(api)
    if text:
        blocks.append(
            {"type": "input_text" if api == "responses" else "text", "text": text}
        )
    key = "input" if api == "responses" else "messages"
    expected: list[dict[str, object]] = [{"role": "user", "content": blocks}]
    if api in {"compatible", "openai_chat"}:
        expected.insert(
            0,
            {
                "role": "system" if api == "compatible" else "developer",
                "content": "System prompt",
            },
        )
    assert payload[key] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", ["5m", "1h"])
@pytest.mark.parametrize("text", ["Historical images", ""])
async def test_anthropic_cache_marker_preserves_image_blocks(
    ttl: Literal["5m", "1h"], text: str
) -> None:
    default_adapter, _ = provider("anthropic")
    adapter = AnthropicProvider(
        default_adapter.config, "test-key", stable_prefix_cache_ttl=ttl
    )
    payload = await capture(
        "anthropic", [message(text, images()), message("Follow-up")], adapter
    )
    cache_control = {"type": "ephemeral"}
    if ttl == "1h":
        cache_control["ttl"] = ttl
    blocks = image_blocks("anthropic")
    if text:
        blocks.append({"type": "text", "text": text})
    blocks[-1]["cache_control"] = cache_control
    assert payload["messages"] == [
        {"role": "user", "content": blocks},
        {"role": "user", "content": "Follow-up"},
    ]
    assert payload["system"] == [
        {"type": "text", "text": "System prompt", "cache_control": cache_control}
    ]
    assert "cache_control" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["anthropic", "compatible", "openai_chat", "responses"])
@pytest.mark.parametrize(
    "invalid",
    ["empty", "unsupported", "mismatch", "oversized", "count", "total", "assistant"],
)
@pytest.mark.parametrize("historical", [False, True])
async def test_rejects_invalid_images_before_http(
    api: Api, invalid: str, historical: bool
) -> None:
    adapter, url = provider(api)
    bad_message, error_text = invalid_message(invalid)
    messages = [bad_message, message("Follow-up")] if historical else [bad_message]
    with respx.mock(assert_all_called=False) as router:
        router.post(url).mock(return_value=response(api))
        with pytest.raises(UnknownProviderError, match=error_text) as caught:
            _ = [
                chunk async for chunk in adapter.stream(messages, None, "unknown-model")
            ]
        assert router.calls.call_count == 0
    if invalid != "assistant":
        assert isinstance(caught.value.__cause__, ValueError)


def invalid_message(invalid: str) -> tuple[Message, str]:
    image = images()[0]
    match invalid:
        case "empty":
            return message("Question", (replace(image, data=b""),)), "empty"
        case "unsupported":
            return message(
                "Question", (replace(image, data=b"not an image"),)
            ), "Unsupported"
        case "mismatch":
            return message(
                "Question", (replace(image, media_type="image/jpeg"),)
            ), "media type"
        case "oversized":
            oversized = replace(image, data=image.data + b"\0" * MAX_IMAGE_BYTES)
            return message("Question", (oversized,)), "5 MiB"
        case "count":
            return message("Question", (image,) * (MAX_IMAGES + 1)), "At most 10"
        case "total":
            large = replace(
                image, data=(image.data + b"\0" * MAX_IMAGE_BYTES)[:MAX_IMAGE_BYTES]
            )
            count = MAX_MESSAGE_IMAGE_BYTES // MAX_IMAGE_BYTES + 1
            return message("Question", (large,) * count), "20 MiB"
        case "assistant":
            return message("Answer", images(), "assistant"), "user"
        case _:
            raise AssertionError(f"Unknown test case: {invalid}")


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["anthropic", "compatible", "openai_chat", "responses"])
async def test_preserves_historical_images_across_turns(api: Api) -> None:
    payload = await capture(
        api,
        [
            message("Prior question", images()),
            message("Prior answer", role="assistant"),
            message("", tuple(reversed(images()))),
        ],
    )
    blocks = image_blocks(api)
    old_blocks = [
        *blocks,
        {
            "type": "input_text" if api == "responses" else "text",
            "text": "Prior question",
        },
    ]
    expected: list[dict[str, object]] = [
        {"role": "user", "content": old_blocks},
        {"role": "assistant", "content": "Prior answer"},
        {"role": "user", "content": list(reversed(blocks))},
    ]
    if api in {"compatible", "openai_chat"}:
        expected.insert(
            0,
            {
                "role": "system" if api == "compatible" else "developer",
                "content": "System prompt",
            },
        )
    assert payload["input" if api == "responses" else "messages"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["anthropic", "compatible", "openai_chat", "responses"])
async def test_text_only_payload_is_unchanged(api: Api) -> None:
    payload = await capture(
        api,
        [
            message(""),
            message("Prior answer", role="assistant"),
            message("Next question"),
        ],
    )
    turns = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "Prior answer"},
        {"role": "user", "content": "Next question"},
    ]
    expected: dict[str, object] = {"model": "unknown-model", "stream": True}
    if api == "responses":
        expected.update(
            input=turns,
            instructions="System prompt",
            max_output_tokens=4096,
            store=False,
        )
    elif api == "anthropic":
        expected.update(
            messages=turns, system="System prompt", max_tokens=4096, temperature=1.0
        )
    else:
        expected["messages"] = [
            {
                "role": "system" if api == "compatible" else "developer",
                "content": "System prompt",
            },
            *turns,
        ]
        expected["stream_options"] = {"include_usage": True}
        expected["max_tokens" if api == "compatible" else "max_completion_tokens"] = (
            4096
        )
        if api == "compatible":
            expected["temperature"] = 1.0
    assert payload == expected
