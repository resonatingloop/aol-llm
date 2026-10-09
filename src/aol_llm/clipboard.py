"""Bounded, read-only Linux image clipboard access."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import replace

from aol_llm._x11_clipboard import read_x11_image
from aol_llm.core.images import MAX_IMAGE_BYTES, image_from_bytes
from aol_llm.core.types import ImageAttachment

_TIMEOUT_SECONDS = 5.0
_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")


async def _run(command: tuple[str, ...], limit: int) -> bytes:
    process = None
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            assert process.stdout is not None
            data = bytearray()
            while chunk := await process.stdout.read(min(65536, limit + 1 - len(data))):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError(
                        "Clipboard image is too large; choose a smaller image."
                    )
            if await process.wait() != 0:
                raise ValueError(
                    "Clipboard reader failed; copy an image again or use the file picker."
                )
            return bytes(data)
    except TimeoutError as error:
        raise ValueError(
            "Clipboard read timed out; copy the image again or use the file picker."
        ) from error
    except OSError as error:
        raise ValueError(
            "Clipboard reader unavailable; use the file picker or install clipboard tools."
        ) from error
    finally:
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass  # The child exited between the returncode check and kill.
            await process.wait()


async def _read_bytes() -> bytes:
    listing: tuple[str, ...]
    prefix: tuple[str, ...]
    executable = shutil.which("wl-paste") if os.environ.get("WAYLAND_DISPLAY") else None
    if executable is not None:
        listing = (executable, "--list-types")
        prefix = (executable, "--no-newline", "--type")
    elif os.environ.get("DISPLAY"):
        executable = shutil.which("xclip")
        if executable is None:
            return await read_x11_image(_IMAGE_TYPES, MAX_IMAGE_BYTES, _TIMEOUT_SECONDS)
        prefix = (executable, "-selection", "clipboard", "-out", "-target")
        listing = (*prefix, "TARGETS")
    else:
        raise ValueError(
            "Install wl-clipboard or attach an image using the file picker."
        )
    try:
        targets = (await _run(listing, 16384)).decode().splitlines()
    except UnicodeDecodeError as error:
        raise ValueError(
            "Clipboard targets are invalid; copy an image again or use the file picker."
        ) from error
    media_type = next((kind for kind in _IMAGE_TYPES if kind in targets), None)
    if media_type is None:
        raise ValueError(
            "No supported image in clipboard; copy a PNG, JPEG, GIF or WebP image."
        )
    return await _run((*prefix, media_type), MAX_IMAGE_BYTES)


async def read_clipboard_image() -> ImageAttachment:
    """Read a supported image without changing clipboard ownership or contents."""
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            data = await _read_bytes()
    except TimeoutError as error:
        raise ValueError(
            "Clipboard read timed out; copy the image again or use the file picker."
        ) from error
    try:
        image = image_from_bytes(data, "clipboard")
    except ValueError as error:
        raise ValueError(
            f"Invalid clipboard image: {error}; copy a supported image or use the file picker."
        ) from error
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    return replace(image, name=f"clipboard.{extension[image.media_type]}")
