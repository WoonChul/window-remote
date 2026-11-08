"""Platform backends: window listing, capture and input injection."""

from __future__ import annotations

import sys

from .base import Backend, WindowInfo


def create(mock: bool = False) -> Backend:
    if mock:
        from .mock import MockBackend
        return MockBackend()
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    raise RuntimeError("현재는 Windows만 지원합니다. 테스트용으로는 --mock 옵션을 쓰세요.")


__all__ = ["Backend", "WindowInfo", "create"]
