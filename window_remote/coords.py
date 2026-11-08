"""Coordinate conversion between client frames and the host screen.

Clients send positions normalized to the captured window (0.0 - 1.0), so the
agent can downscale frames freely and still hit the exact host pixel.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def norm_to_screen(nx: float, ny: float, rect: Rect) -> tuple[int, int]:
    """Map a normalized window position to an absolute screen pixel."""
    nx = _clamp(float(nx), 0.0, 1.0)
    ny = _clamp(float(ny), 0.0, 1.0)
    x = rect.left + min(int(nx * rect.width), rect.width - 1)
    y = rect.top + min(int(ny * rect.height), rect.height - 1)
    return x, y


def fit_size(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Size of a frame after limiting its width (0 = no limit)."""
    if max_width <= 0 or width <= max_width:
        return width, height
    return max_width, max(1, round(height * max_width / width))
