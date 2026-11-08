"""Fake backend for development and tests on any OS (python -m window_remote --mock).

Draws synthetic windows and records every input event it receives.
"""

from __future__ import annotations

import threading
import time

from PIL import Image, ImageDraw

from ..coords import Rect
from .base import Backend, WindowInfo


class MockBackend(Backend):
    name = "mock"
    capture_methods = ("screen", "window")

    def __init__(self) -> None:
        self._windows = {
            1001: (WindowInfo(1001, "Mock 메모장", "notepad.exe", 4001), Rect(100, 100, 800, 600)),
            1002: (WindowInfo(1002, "Mock CAD", "cad.exe", 4002), Rect(950, 50, 1280, 720)),
        }
        self.events: list[tuple] = []
        self.cursor = (0, 0)
        self.foreground: int | None = None
        self.minimized: set[int] = set()
        self.typed = ""
        self._lock = threading.Lock()

    def _log(self, *event) -> None:
        with self._lock:
            self.events.append(event)

    # --- windows -----------------------------------------------------------
    def list_windows(self) -> list[WindowInfo]:
        return [info for info, _ in self._windows.values()]

    def window_info(self, hwnd: int) -> WindowInfo | None:
        entry = self._windows.get(hwnd)
        return entry[0] if entry else None

    def get_rect(self, hwnd: int) -> Rect | None:
        entry = self._windows.get(hwnd)
        return entry[1] if entry else None

    def is_minimized(self, hwnd: int) -> bool:
        return hwnd in self.minimized

    def focus(self, hwnd: int) -> bool:
        if hwnd not in self._windows:
            return False
        self.minimized.discard(hwnd)
        if self.foreground != hwnd:
            self.foreground = hwnd
            self._log("focus", hwnd)
        return True

    def close_window(self, hwnd: int) -> None:
        self._windows.pop(hwnd, None)

    # --- capture -------------------------------------------------------------
    def capture(self, hwnd: int, method: str) -> Image.Image | None:
        entry = self._windows.get(hwnd)
        if not entry:
            return None
        info, rect = entry
        img = Image.new("RGB", (rect.width, rect.height), (245, 245, 240))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, rect.width - 1, 30), fill=(40, 90, 160))
        d.text((10, 8), f"{info.title}  [{method}]", fill=(255, 255, 255))
        for gx in range(0, rect.width, 50):
            d.line((gx, 31, gx, rect.height), fill=(220, 220, 215))
        for gy in range(31, rect.height, 50):
            d.line((0, gy, rect.width, gy), fill=(220, 220, 215))
        d.text((10, 40), f"time {time.strftime('%H:%M:%S')}", fill=(0, 0, 0))
        d.text((10, 60), f"typed: {self.typed[-60:]}", fill=(0, 0, 0))
        cx, cy = self.cursor[0] - rect.left, self.cursor[1] - rect.top
        if 0 <= cx < rect.width and 0 <= cy < rect.height:
            d.line((cx - 10, cy, cx + 10, cy), fill=(220, 0, 0), width=2)
            d.line((cx, cy - 10, cx, cy + 10), fill=(220, 0, 0), width=2)
        return img

    # --- input -----------------------------------------------------------------
    def mouse_move(self, x: int, y: int) -> None:
        self.cursor = (x, y)
        self._log("move", x, y)

    def mouse_button(self, button: str, down: bool) -> None:
        self._log("button", button, down, *self.cursor)

    def mouse_wheel(self, delta: int, horizontal: bool = False) -> None:
        self._log("wheel", delta, horizontal)

    def key(self, vk: int, down: bool, extended: bool = False) -> None:
        self._log("key", vk, down, extended)

    def text(self, s: str) -> None:
        self.typed += s
        self._log("text", s)
