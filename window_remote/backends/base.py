"""Backend interface. One backend instance is shared by all sessions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from ..coords import Rect


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    exe: str
    pid: int

    def to_json(self) -> dict:
        return {"hwnd": self.hwnd, "title": self.title, "exe": self.exe, "pid": self.pid}


class Backend(ABC):
    name = "base"
    capture_methods: tuple[str, ...] = ("screen",)

    # --- windows -------------------------------------------------------
    @abstractmethod
    def list_windows(self) -> list[WindowInfo]: ...

    @abstractmethod
    def window_info(self, hwnd: int) -> WindowInfo | None: ...

    @abstractmethod
    def get_rect(self, hwnd: int) -> Rect | None:
        """Visible bounds of the window in physical screen pixels."""

    @abstractmethod
    def is_minimized(self, hwnd: int) -> bool: ...

    @abstractmethod
    def focus(self, hwnd: int) -> bool:
        """Restore and bring the window to the foreground."""

    # --- capture (called from a worker thread) -------------------------
    @abstractmethod
    def capture(self, hwnd: int, method: str) -> Image.Image | None: ...

    # --- input ----------------------------------------------------------
    @abstractmethod
    def mouse_move(self, x: int, y: int) -> None: ...

    @abstractmethod
    def mouse_button(self, button: str, down: bool) -> None: ...

    @abstractmethod
    def mouse_wheel(self, delta: int, horizontal: bool = False) -> None: ...

    @abstractmethod
    def key(self, vk: int, down: bool, extended: bool = False) -> None: ...

    @abstractmethod
    def text(self, s: str) -> None:
        """Type unicode text directly (works for Korean without an IME)."""
