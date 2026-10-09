"""Read CLIPBOARD through libX11, including ICCCM incremental transfers.

Only a private requestor window's properties are changed, never the selection.
Xlib calls are synchronous local-server operations; event waits yield to asyncio.
"""

import asyncio
import ctypes
from collections.abc import Callable


class _Selection(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("requestor", ctypes.c_ulong),
        ("selection", ctypes.c_ulong),
        ("target", ctypes.c_ulong),
        ("property", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
    ]


class _Property(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("atom", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("state", ctypes.c_int),
    ]


class _Event(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("selection", _Selection),
        ("property", _Property),
        ("pad", ctypes.c_long * 24),
    ]


def _bind(lib: ctypes.CDLL) -> None:
    pointer, ulong, integer = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int
    bindings = (
        ("XOpenDisplay", pointer, [ctypes.c_char_p]),
        ("XDefaultRootWindow", ulong, [pointer]),
        (
            "XCreateSimpleWindow",
            ulong,
            [
                pointer,
                ulong,
                integer,
                integer,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ulong,
                ulong,
            ],
        ),
        ("XSelectInput", integer, [pointer, ulong, ctypes.c_long]),
        ("XInternAtom", ulong, [pointer, ctypes.c_char_p, integer]),
        ("XGetSelectionOwner", ulong, [pointer, ulong]),
        ("XConvertSelection", integer, [pointer] + [ulong] * 5),
        ("XPending", integer, [pointer]),
        ("XNextEvent", integer, [pointer, ctypes.POINTER(_Event)]),
        (
            "XGetWindowProperty",
            integer,
            [
                pointer,
                ulong,
                ulong,
                ctypes.c_long,
                ctypes.c_long,
                integer,
                ulong,
                ctypes.POINTER(ulong),
                ctypes.POINTER(integer),
                ctypes.POINTER(ulong),
                ctypes.POINTER(ulong),
                ctypes.POINTER(pointer),
            ],
        ),
        ("XDeleteProperty", integer, [pointer, ulong, ulong]),
        ("XFree", integer, [pointer]),
        ("XFlush", integer, [pointer]),
        ("XDestroyWindow", integer, [pointer, ulong]),
        ("XCloseDisplay", integer, [pointer]),
    )
    for name, result, args in bindings:
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args


async def _next_event(
    lib: ctypes.CDLL, display: int, matches: Callable[[_Event], bool]
) -> _Event:
    while True:
        for _ in range(64):
            if not lib.XPending(display):
                break
            event = _Event()
            lib.XNextEvent(display, ctypes.byref(event))
            if matches(event):
                return event
        await asyncio.sleep(0.005)


def _property(
    lib: ctypes.CDLL, display: int, window: int, prop: int, limit: int
) -> tuple[int, int, bytes | list[int]]:
    kind, count, remaining = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
    fmt, value = ctypes.c_int(), ctypes.c_void_p()
    status = lib.XGetWindowProperty(
        display,
        window,
        prop,
        0,
        (limit + 3) // 4,
        0,
        0,
        ctypes.byref(kind),
        ctypes.byref(fmt),
        ctypes.byref(count),
        ctypes.byref(remaining),
        ctypes.byref(value),
    )
    try:
        if status != 0:
            raise ValueError("Clipboard image could not be read; copy it again.")
        if remaining.value or count.value * (fmt.value // 8) > limit:
            raise ValueError("Clipboard image is too large; choose a smaller image.")
        if fmt.value == 32:
            numbers = ctypes.cast(value, ctypes.POINTER(ctypes.c_ulong))
            data: bytes | list[int] = [
                int(numbers[index]) for index in range(count.value)
            ]
        elif fmt.value == 8:
            data = ctypes.string_at(value, count.value) if count.value else b""
        else:
            raise ValueError("Clipboard image has an invalid format; copy it again.")
        return kind.value, fmt.value, data
    finally:
        if value.value:
            lib.XFree(value)


async def _transfer(
    lib: ctypes.CDLL,
    display: int,
    window: int,
    selection: int,
    target: int,
    prop: int,
    expected: int,
    limit: int,
) -> bytes | list[int]:
    lib.XDeleteProperty(display, window, prop)
    lib.XConvertSelection(display, selection, target, prop, window, 0)
    lib.XFlush(display)
    event = await _next_event(
        lib,
        display,
        lambda event: (
            event.type == 31
            and event.selection.requestor == window
            and event.selection.selection == selection
            and event.selection.target == target
        ),
    )
    if event.selection.property != prop:
        raise ValueError(
            "No supported image in clipboard; copy an image or use the file picker."
        )
    kind, fmt, data = _property(lib, display, window, prop, limit)
    incr = int(lib.XInternAtom(display, b"INCR", 0))
    if kind != incr:
        if kind != expected:
            raise ValueError("Clipboard image has an invalid format; copy it again.")
        return data
    if fmt != 32 or not isinstance(data, list) or len(data) != 1:
        raise ValueError(
            "Clipboard incremental transfer is invalid; copy the image again."
        )
    if data[0] > limit:
        raise ValueError("Clipboard image is too large; choose a smaller image.")
    result_bytes = bytearray()
    result_numbers: list[int] = []
    result_format = 0
    total = 0
    while True:
        lib.XDeleteProperty(display, window, prop)
        lib.XFlush(display)
        await _next_event(
            lib,
            display,
            lambda event: (
                event.type == 28
                and event.property.window == window
                and event.property.atom == prop
                and event.property.state == 0
            ),
        )
        kind, fmt, data = _property(lib, display, window, prop, limit - total)
        if kind != expected or (result_format and result_format != fmt):
            raise ValueError(
                "Clipboard incremental transfer is invalid; copy the image again."
            )
        result_format = fmt
        if not data:
            return bytes(result_bytes) if fmt == 8 else result_numbers
        if isinstance(data, bytes):
            result_bytes.extend(data)
            total += len(data)
        else:
            result_numbers.extend(data)
            total += len(data) * 4


async def read_x11_image(
    media_types: tuple[str, ...], limit: int, timeout: float
) -> bytes:
    try:
        lib = ctypes.CDLL("libX11.so.6")
    except OSError as error:
        raise ValueError(
            "Clipboard tools and libX11 unavailable; install wl-clipboard/xclip or use the file picker."
        ) from error
    _bind(lib)
    display = int(lib.XOpenDisplay(None) or 0)
    if not display:
        raise ValueError(
            "Cannot connect to the X11 clipboard; use the file picker or install wl-clipboard."
        )
    window = 0
    try:
        async with asyncio.timeout(timeout):
            root = int(lib.XDefaultRootWindow(display))
            window = int(lib.XCreateSimpleWindow(display, root, 0, 0, 1, 1, 0, 0, 0))
            lib.XSelectInput(display, window, 1 << 22)
            selection = int(lib.XInternAtom(display, b"CLIPBOARD", 0))
            if not lib.XGetSelectionOwner(display, selection):
                raise ValueError(
                    "No image in clipboard; copy an image or use the file picker."
                )
            targets_atom = int(lib.XInternAtom(display, b"TARGETS", 0))
            prop = int(lib.XInternAtom(display, b"_AOL_LLM_CLIPBOARD", 0))
            atoms = await _transfer(
                lib,
                display,
                window,
                selection,
                targets_atom,
                prop,
                int(lib.XInternAtom(display, b"ATOM", 0)),
                16384,
            )
            if not isinstance(atoms, list):
                raise ValueError(
                    "Clipboard image targets are invalid; copy the image again."
                )
            for media_type in media_types:
                target = int(lib.XInternAtom(display, media_type.encode(), 0))
                if target in atoms:
                    data = await _transfer(
                        lib, display, window, selection, target, prop, target, limit
                    )
                    if isinstance(data, bytes):
                        return data
                    raise ValueError(
                        "Clipboard image has an invalid format; copy it again."
                    )
            raise ValueError(
                "No supported image in clipboard; copy a PNG, JPEG, GIF or WebP image."
            )
    except TimeoutError as error:
        raise ValueError(
            "Clipboard read timed out; copy the image again or use the file picker."
        ) from error
    finally:
        if window:
            lib.XDestroyWindow(display, window)
        lib.XCloseDisplay(display)
