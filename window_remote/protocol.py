"""Wire format shared by the agent and clients. See docs/protocol.md."""

from __future__ import annotations

import struct

PROTOCOL_VERSION = 1

# Binary messages (agent -> client)
MSG_FRAME = 1

# type (u8), seq (u32), width (u16), height (u16), little endian
FRAME_HEADER = struct.Struct("<BIHH")


def pack_frame(seq: int, width: int, height: int, jpeg: bytes) -> bytes:
    return FRAME_HEADER.pack(MSG_FRAME, seq & 0xFFFFFFFF, width, height) + jpeg


def unpack_frame(data: bytes) -> tuple[int, int, int, bytes]:
    kind, seq, width, height = FRAME_HEADER.unpack_from(data)
    if kind != MSG_FRAME:
        raise ValueError(f"not a frame message: {kind}")
    return seq, width, height, data[FRAME_HEADER.size:]


MOUSE_BUTTONS = ("left", "right", "middle")
CAPTURE_METHODS = ("screen", "window")
