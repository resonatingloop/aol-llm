"""Clipboard tests use synthetic data, never the desktop clipboard."""

import asyncio
import base64
import ctypes
import shutil
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import cast

import pytest
import pytest_asyncio

from aol_llm import _x11_clipboard, clipboard

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8A"
    "AwMCAO+aBZkAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def no_live_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)


@pytest.mark.asyncio
async def test_wayland_reads_advertised_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic-wayland")
    monkeypatch.setenv("DISPLAY", ":synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: f"/synthetic/{name}")
    calls: list[tuple[str, ...]] = []

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        calls.append(command)
        return b"text/plain\nimage/png\n" if "--list-types" in command else PNG

    monkeypatch.setattr(clipboard, "_run", run)
    image = await clipboard.read_clipboard_image()
    assert image.data == PNG
    assert image.media_type == "image/png"
    assert image.name == "clipboard.png"
    assert calls == [
        ("/synthetic/wl-paste", "--list-types"),
        ("/synthetic/wl-paste", "--no-newline", "--type", "image/png"),
    ]


@pytest.mark.asyncio
async def test_command_reads_binary_without_shell() -> None:
    command = (
        sys.executable,
        "-c",
        "import sys; sys.stdout.buffer.write(b'\\x00\\xff')",
    )
    assert await clipboard._run(command, 100) == b"\x00\xff"


@pytest.mark.asyncio
async def test_command_enforces_byte_limit() -> None:
    command = (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 101)")
    with pytest.raises(ValueError, match="too large"):
        await clipboard._run(command, 100)


@pytest.mark.asyncio
async def test_command_reports_failed_reader_without_stderr() -> None:
    command = (
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('private'); sys.exit(2)",
    )
    with pytest.raises(ValueError, match="copy.*image") as error:
        await clipboard._run(command, 100)
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_command_timeout_kills_and_reaps_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clipboard, "_TIMEOUT_SECONDS", 0.03, raising=False)
    command = (sys.executable, "-c", "import time; time.sleep(0.15)")
    with pytest.raises(ValueError, match="timed out"):
        await clipboard._run(command, 100)


@pytest.mark.asyncio
async def test_command_cancellation_reaps_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []
    started = asyncio.Event()

    async def spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        child = await create(*args, **kwargs)  # type: ignore[arg-type]
        children.append(child)
        started.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(
        clipboard._run((sys.executable, "-c", "import time; time.sleep(1)"), 100)
    )
    await started.wait()
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert children[0].returncode is not None
    finally:
        if children[0].returncode is None:
            children[0].kill()
        await children[0].wait()


class _Request(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("owner", ctypes.c_ulong),
        ("requestor", ctypes.c_ulong),
        ("selection", ctypes.c_ulong),
        ("target", ctypes.c_ulong),
        ("property", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
    ]


class _Notify(ctypes.Structure):
    _fields_ = _Request._fields_[:4] + [
        ("requestor", ctypes.c_ulong),
        ("selection", ctypes.c_ulong),
        ("target", ctypes.c_ulong),
        ("property", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
    ]


class _Property(ctypes.Structure):
    _fields_ = _Request._fields_[:4] + [
        ("window", ctypes.c_ulong),
        ("atom", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("state", ctypes.c_int),
    ]


class _Event(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("request", _Request),
        ("notify", _Notify),
        ("property", _Property),
        ("pad", ctypes.c_long * 24),
    ]


@dataclass
class _Owner:
    data: bytes = PNG
    incremental: bool = False
    advertised_size: int | None = None
    targets: tuple[str, ...] = ("image/png",)
    refuse: bool = False
    stall: bool = False
    stall_incremental: bool = False
    received: asyncio.Event = field(default_factory=asyncio.Event)


@pytest_asyncio.fixture
async def x11_owner(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Owner]:
    executable = shutil.which("Xvfb")
    if executable is None:
        pytest.skip("Xvfb unavailable; synthetic X11 integration requires it")
    try:
        lib = ctypes.CDLL("libX11.so.6")
    except OSError:
        pytest.skip("libX11 unavailable")
    server = await asyncio.create_subprocess_exec(
        executable,
        "-displayfd",
        "1",
        "-screen",
        "0",
        "64x64x24",
        "-nolisten",
        "tcp",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert server.stdout is not None
    display_number = (
        (await asyncio.wait_for(server.stdout.readline(), 5)).decode().strip()
    )
    monkeypatch.setenv("DISPLAY", f":{display_number}")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    bindings = (
        ("XOpenDisplay", ctypes.c_void_p, [ctypes.c_char_p]),
        ("XDefaultRootWindow", ctypes.c_ulong, [ctypes.c_void_p]),
        (
            "XCreateSimpleWindow",
            ctypes.c_ulong,
            [ctypes.c_void_p] + [ctypes.c_ulong] * 8,
        ),
        (
            "XInternAtom",
            ctypes.c_ulong,
            [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int],
        ),
        ("XSetSelectionOwner", ctypes.c_int, [ctypes.c_void_p] + [ctypes.c_ulong] * 3),
        ("XGetSelectionOwner", ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_ulong]),
        ("XPending", ctypes.c_int, [ctypes.c_void_p]),
        ("XNextEvent", ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(_Event)]),
        (
            "XSelectInput",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_long],
        ),
        (
            "XChangeProperty",
            ctypes.c_int,
            [ctypes.c_void_p]
            + [ctypes.c_ulong] * 3
            + [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int],
        ),
        (
            "XSendEvent",
            ctypes.c_int,
            [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_long,
                ctypes.POINTER(_Event),
            ],
        ),
        ("XFlush", ctypes.c_int, [ctypes.c_void_p]),
        ("XCloseDisplay", ctypes.c_int, [ctypes.c_void_p]),
        (
            "XQueryTree",
            ctypes.c_int,
            [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                ctypes.POINTER(ctypes.c_uint),
            ],
        ),
        ("XFree", ctypes.c_int, [ctypes.c_void_p]),
    )
    for name, result, args in bindings:
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args
    display = lib.XOpenDisplay(f":{display_number}".encode())
    assert display
    root = lib.XDefaultRootWindow(display)
    window = lib.XCreateSimpleWindow(display, root, 0, 0, 1, 1, 0, 0, 0)

    def atom(name: str) -> int:
        return int(lib.XInternAtom(display, name.encode(), 0))

    selection, targets, png, incr = map(
        atom, ("CLIPBOARD", "TARGETS", "image/png", "INCR")
    )
    lib.XSetSelectionOwner(display, selection, window, 0)
    assert lib.XGetSelectionOwner(display, selection) == window
    owner = _Owner()
    streams: dict[tuple[int, int], list[bytes]] = {}

    def change(requestor: int, prop: int, kind: int, data: bytes | list[int]) -> None:
        value = (
            ctypes.create_string_buffer(data)
            if isinstance(data, bytes)
            else ((ctypes.c_ulong * len(data))(*data))
        )
        lib.XChangeProperty(
            display,
            requestor,
            prop,
            kind,
            8 if isinstance(data, bytes) else 32,
            0,
            value,
            len(data),
        )
        lib.XFlush(display)

    async def serve() -> None:
        while True:
            while lib.XPending(display):
                event = _Event()
                lib.XNextEvent(display, ctypes.byref(event))
                if event.type == 30:  # SelectionRequest
                    request = event.request
                    if owner.stall or request.target != targets:
                        owner.received.set()
                    if owner.stall:
                        continue
                    prop = int(request.property or request.target)
                    if request.target == targets:
                        change(
                            request.requestor,
                            prop,
                            atom("ATOM"),
                            list(map(atom, owner.targets)),
                        )
                    elif owner.refuse:
                        prop = 0
                    elif owner.incremental:
                        lib.XSelectInput(display, request.requestor, (1 << 22))
                        streams[(request.requestor, prop)] = [
                            owner.data[index : index + 11]
                            for index in range(0, len(owner.data), 11)
                        ] + [b""]
                        change(
                            request.requestor,
                            prop,
                            incr,
                            [
                                owner.advertised_size
                                if owner.advertised_size is not None
                                else len(owner.data)
                            ],
                        )
                    else:
                        change(request.requestor, prop, request.target, owner.data)
                    reply = _Event()
                    reply.notify = _Notify(
                        31,
                        0,
                        1,
                        display,
                        request.requestor,
                        request.selection,
                        request.target,
                        prop,
                        request.time,
                    )
                    lib.XSendEvent(
                        display, request.requestor, 0, 0, ctypes.byref(reply)
                    )
                    lib.XFlush(display)
                elif event.type == 28 and event.property.state == 1:  # PropertyDelete
                    if owner.stall_incremental:
                        continue
                    key = (event.property.window, event.property.atom)
                    if chunks := streams.get(key):
                        change(*key, png, chunks.pop(0))
            await asyncio.sleep(0.001)

    task = asyncio.create_task(serve())
    try:
        yield owner
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        try:
            assert lib.XGetSelectionOwner(display, selection) == window
            tree_root, parent, count = (
                ctypes.c_ulong(),
                ctypes.c_ulong(),
                ctypes.c_uint(),
            )
            children = ctypes.POINTER(ctypes.c_ulong)()
            lib.XQueryTree(
                display,
                root,
                ctypes.byref(tree_root),
                ctypes.byref(parent),
                ctypes.byref(children),
                ctypes.byref(count),
            )
            try:
                assert [int(children[index]) for index in range(count.value)] == [
                    window
                ]
            finally:
                lib.XFree(children)
        finally:
            lib.XCloseDisplay(display)
            server.terminate()
            await server.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("incremental", [False, True])
async def test_x11_reads_synthetic_selection(
    x11_owner: _Owner, incremental: bool
) -> None:
    x11_owner.incremental = incremental
    image = await clipboard.read_clipboard_image()
    assert (image.data, image.media_type, image.name) == (
        PNG,
        "image/png",
        "clipboard.png",
    )


@pytest.mark.asyncio
async def test_xclip_reads_advertised_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY", ":synthetic")
    monkeypatch.setattr(
        shutil, "which", lambda name: "/synthetic/xclip" if name == "xclip" else None
    )
    calls: list[tuple[str, ...]] = []

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        calls.append(command)
        return b"TARGETS\nimage/png\n" if command[-1] == "TARGETS" else PNG

    monkeypatch.setattr(clipboard, "_run", run)
    image = await clipboard.read_clipboard_image()
    assert image.data == PNG
    assert calls == [
        ("/synthetic/xclip", "-selection", "clipboard", "-out", "-target", "TARGETS"),
        ("/synthetic/xclip", "-selection", "clipboard", "-out", "-target", "image/png"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"", b"not an image"])
async def test_invalid_image_is_actionable(
    data: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/wl-paste")

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        return b"image/png\n" if "--list-types" in command else data

    monkeypatch.setattr(clipboard, "_run", run)
    with pytest.raises(ValueError, match="copy.*image"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_invalid_target_encoding_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/wl-paste")

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        return b"\xff"

    monkeypatch.setattr(clipboard, "_run", run)
    with pytest.raises(ValueError, match="copy.*image"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["normal", "advertised", "actual"])
async def test_x11_byte_limits(
    x11_owner: _Owner, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clipboard, "MAX_IMAGE_BYTES", len(PNG) - 1)
    x11_owner.incremental = mode != "normal"
    x11_owner.advertised_size = 0 if mode == "actual" else len(PNG)
    with pytest.raises(ValueError, match="too large"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
@pytest.mark.parametrize("incremental", [False, True])
async def test_x11_timeout_and_cleanup(
    x11_owner: _Owner, incremental: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clipboard, "_TIMEOUT_SECONDS", 0.05)
    x11_owner.incremental = incremental
    x11_owner.stall = not incremental
    x11_owner.stall_incremental = incremental
    with pytest.raises(ValueError, match="timed out"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_x11_no_image_is_actionable(x11_owner: _Owner) -> None:
    x11_owner.targets = ("text/plain",)
    with pytest.raises(ValueError, match="No supported image"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_x11_refused_image_is_actionable(x11_owner: _Owner) -> None:
    x11_owner.refuse = True
    with pytest.raises(ValueError, match="copy.*image"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_no_desktop_is_actionable() -> None:
    with pytest.raises(ValueError, match="file picker"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_missing_lib_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY", ":synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    def missing(name: str) -> ctypes.CDLL:
        raise OSError("synthetic missing libX11")

    monkeypatch.setattr(ctypes, "CDLL", missing)
    with pytest.raises(ValueError, match="libX11 unavailable.*file picker"):
        await clipboard.read_clipboard_image()


@pytest.mark.asyncio
async def test_command_exact_limit() -> None:
    command = (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 100)")
    assert await clipboard._run(command, 100) == b"x" * 100


@pytest.mark.asyncio
async def test_unavailable_command_is_actionable() -> None:
    with pytest.raises(ValueError, match="unavailable.*file picker"):
        await clipboard._run(("/synthetic/nonexistent-clipboard-tool",), 100)


@pytest.mark.asyncio
async def test_x11_event_flood_yields_to_event_loop() -> None:
    class Flood:
        def XPending(self, display: int) -> int:
            return 1

        def XNextEvent(self, display: int, event: object) -> int:
            return 0

    yielded = asyncio.Event()
    asyncio.get_running_loop().call_soon(yielded.set)
    visits = 0

    def matches(event: _x11_clipboard._Event) -> bool:
        nonlocal visits
        visits += 1
        return visits == 65

    await _x11_clipboard._next_event(cast(ctypes.CDLL, Flood()), 0, matches)
    assert yielded.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("incremental", [False, True])
async def test_x11_cancellation_cleans_requestor(
    x11_owner: _Owner, incremental: bool
) -> None:
    x11_owner.stall = not incremental
    x11_owner.incremental = incremental
    x11_owner.stall_incremental = incremental
    task = asyncio.create_task(clipboard.read_clipboard_image())
    await asyncio.wait_for(x11_owner.received.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # The fixture checks that only the owner's window remains and ownership is unchanged.


@pytest.mark.asyncio
async def test_wayland_without_tool_uses_xwayland_bridge(
    x11_owner: _Owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    image = await clipboard.read_clipboard_image()
    assert image.data == PNG


@pytest.mark.asyncio
async def test_deadline_covers_target_negotiation_and_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/wl-paste")
    monkeypatch.setattr(clipboard, "_TIMEOUT_SECONDS", 0.06)
    calls = 0

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.04)
        return b"image/png\n" if "--list-types" in command else PNG

    monkeypatch.setattr(clipboard, "_run", run)
    with pytest.raises(ValueError, match="timed out"):
        await clipboard.read_clipboard_image()
    assert calls == 2


@pytest.mark.asyncio
async def test_only_exact_supported_targets_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/wl-paste")
    calls: list[tuple[str, ...]] = []

    async def run(command: tuple[str, ...], limit: int) -> bytes:
        calls.append(command)
        return b"text/plain\nx-image/png\n"

    monkeypatch.setattr(clipboard, "_run", run)
    with pytest.raises(ValueError, match="No supported image"):
        await clipboard.read_clipboard_image()
    assert len(calls) == 1
