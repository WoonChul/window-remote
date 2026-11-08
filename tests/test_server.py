import asyncio
import json

import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from window_remote.backends.mock import MockBackend
from window_remote.config import Config
from window_remote.protocol import unpack_frame
from window_remote.server import create_app

TOKEN = "test-token"


@pytest.fixture
async def env():
    backend = MockBackend()
    app = create_app(backend, Config(token=TOKEN))
    client = TestClient(TestServer(app))
    await client.start_server()
    yield client, backend
    await client.close()


async def recv_json(ws, kind, timeout=3):
    while True:
        msg = await asyncio.wait_for(ws.receive(), timeout)
        if msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data["t"] == kind:
                return data
        elif msg.type != WSMsgType.BINARY:
            raise AssertionError(f"unexpected {msg.type}")


async def recv_frame(ws, timeout=3):
    while True:
        msg = await asyncio.wait_for(ws.receive(), timeout)
        if msg.type == WSMsgType.BINARY:
            return unpack_frame(msg.data)


async def login(client):
    ws = await client.ws_connect("/ws")
    await ws.send_json({"t": "hello", "token": TOKEN})
    await recv_json(ws, "welcome")
    windows = await recv_json(ws, "windows")
    return ws, windows["items"]


async def test_bad_token_is_rejected(env):
    client, _ = env
    ws = await client.ws_connect("/ws")
    await ws.send_json({"t": "hello", "token": "wrong"})
    err = await recv_json(ws, "error")
    assert err["code"] == "auth"


async def test_index_served(env):
    client, _ = env
    r = await client.get("/")
    assert r.status == 200 and "window-remote" in await r.text()
    r = await client.get("/static/app.js")
    assert r.status == 200


async def test_select_stream_and_click(env):
    client, backend = env
    ws, items = await login(client)
    assert {w["title"] for w in items} == {"Mock 메모장", "Mock CAD"}

    await ws.send_json({"t": "select", "hwnd": 1001})
    sel = await recv_json(ws, "selected")
    assert (sel["w"], sel["h"]) == (800, 600)
    seq, w, h, jpeg = await recv_frame(ws)
    assert (w, h) == (800, 600) and jpeg[:2] == b"\xff\xd8"
    await ws.send_json({"t": "ack", "seq": seq})

    # click in the middle of the window -> host pixel (100+400, 100+300)
    await ws.send_json({"t": "mouse", "a": "down", "b": "left", "x": 0.5, "y": 0.5})
    await ws.send_json({"t": "mouse", "a": "up", "b": "left", "x": 0.5, "y": 0.5})
    await ws.send_json({"t": "text", "s": "안녕"})
    await ws.send_json({"t": "key", "a": "press", "code": "Enter"})
    await ws.send_json({"t": "ping", "ts": 1})
    await recv_json(ws, "pong")

    ev = backend.events
    assert ("button", "left", True, 500, 400) in ev
    assert ("button", "left", False, 500, 400) in ev
    assert ("text", "안녕") in ev
    assert ("key", 0x0D, True, False) in ev and ("key", 0x0D, False, False) in ev
    assert backend.foreground == 1001
    await ws.close()


async def test_downscale_keeps_exact_coordinates(env):
    client, backend = env
    ws, _ = await login(client)
    await ws.send_json({"t": "settings", "maxw": 640, "quality": 50})
    await ws.send_json({"t": "select", "hwnd": 1002})
    await recv_json(ws, "selected")
    _, w, h, _ = await recv_frame(ws)
    assert (w, h) == (640, 360)
    # client clicks pixel (160, 90) of the 640x360 frame = 25% / 25%
    await ws.send_json({"t": "mouse", "a": "down", "x": 160 / 640, "y": 90 / 360})
    await ws.send_json({"t": "ping", "ts": 1})
    await recv_json(ws, "pong")
    assert ("button", "left", True, 950 + 320, 50 + 180) in backend.events
    await ws.close()


async def test_keys_released_on_disconnect(env):
    client, backend = env
    ws, _ = await login(client)
    await ws.send_json({"t": "select", "hwnd": 1001})
    await recv_json(ws, "selected")
    await ws.send_json({"t": "key", "a": "down", "code": "ShiftLeft"})
    await ws.send_json({"t": "mouse", "a": "down", "b": "right", "x": 0.1, "y": 0.1})
    await ws.send_json({"t": "ping", "ts": 1})
    await recv_json(ws, "pong")
    await ws.close()
    for _ in range(50):
        if ("key", 0xA0, False, False) in backend.events:
            break
        await asyncio.sleep(0.02)
    assert ("key", 0xA0, False, False) in backend.events
    assert any(e[:3] == ("button", "right", False) for e in backend.events)


async def test_window_closed(env):
    client, backend = env
    ws, _ = await login(client)
    await ws.send_json({"t": "select", "hwnd": 1001})
    await recv_json(ws, "selected")
    await recv_frame(ws)
    backend.close_window(1001)
    gone = await recv_json(ws, "gone")
    assert gone["hwnd"] == 1001
    await ws.close()


async def test_unchanged_frames_not_resent(env):
    client, backend = env
    backend.capture_count = 0
    orig = backend.capture

    # freeze the picture: same image every time
    img = orig(1001, "screen")
    backend.capture = lambda hwnd, method: img.copy()
    ws, _ = await login(client)
    await ws.send_json({"t": "settings", "fps": 60})
    await ws.send_json({"t": "select", "hwnd": 1001})
    await recv_json(ws, "selected")
    seq, *_ = await recv_frame(ws)
    await ws.send_json({"t": "ack", "seq": seq})
    with pytest.raises(asyncio.TimeoutError):
        await recv_frame(ws, timeout=0.4)
    await ws.close()
