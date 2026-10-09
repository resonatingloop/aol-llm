import base64
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aol_llm.chat import ChatService
from aol_llm.config import default_config
from aol_llm.core.images import image_from_bytes, read_image
from aol_llm.core.types import Message, ProviderConfig, StreamChunk, TokenUsage

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_image_only_send_reopen_and_retry_keep_snapshot(tmp_path: Path) -> None:
    seen: list[list[Message]] = []

    class CapturingProvider:
        config: ProviderConfig

        def __init__(self, config: ProviderConfig) -> None:
            self.config = config

        async def stream(
            self,
            messages: list[Message],
            system: str | None,
            model: str,
            max_output_tokens: int = 4096,
            temperature: float = 1.0,
        ) -> AsyncIterator[StreamChunk]:
            seen.append(messages)
            yield StreamChunk(text="A pixel", done=False)
            yield StreamChunk(text="", done=True, usage=TokenUsage(1, 1, model))

    def factory(
        config: ProviderConfig,
        key: str | None,
        ttl: str | None = None,
    ) -> CapturingProvider:
        return CapturingProvider(config)

    service = ChatService(
        db_path=tmp_path / "chat.db",
        app_config=default_config(),
        provider_factory=factory,
        api_key_getter=lambda provider_id: None,
    )
    service.init()
    chat = service.create_conversation()
    source = tmp_path / "pixel.png"
    source.write_bytes(PNG)
    image = read_image(source)
    _ = [event async for event in service.send_message(chat.id, "", images=(image,))]
    source.unlink()
    reloaded = ChatService(
        db_path=tmp_path / "chat.db",
        app_config=default_config(),
        provider_factory=factory,
        api_key_getter=lambda provider_id: None,
    )
    _ = [event async for event in reloaded.retry_last_response(chat.id)]
    assert len(seen) == 2
    assert seen[0][0].images == seen[1][0].images == (image,)
    assert reloaded.messages(chat.id)[0].images == (image,)
    _ = [event async for event in reloaded.send_message(chat.id, "Explain")]
    assert seen[-1][0].images == (image,)


@pytest.mark.asyncio
async def test_invalid_images_fail_before_message_persistence(tmp_path: Path) -> None:
    service = ChatService(db_path=tmp_path / "chat.db", app_config=default_config())
    service.init()
    chat = service.create_conversation()
    image = image_from_bytes(PNG, "pixel.png")
    with pytest.raises(ValueError, match="10 images"):
        _ = [
            event
            async for event in service.send_message(chat.id, "", images=(image,) * 11)
        ]
    assert service.messages(chat.id) == []
