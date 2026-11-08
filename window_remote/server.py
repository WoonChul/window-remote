"""HTTP + WebSocket server. Serves the web client and runs one Session per connection."""

from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import socket
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import WSMsgType, web
from PIL import Image

from . import __version__, keymap
from .backends.base import Backend
from .config import Config
from .coords import fit_size, norm_to_screen
from .protocol import CAPTURE_METHODS, MOUSE_BUTTONS, PROTOCOL_VERSION, pack_frame

log = logging.getLogger("window_remote")

WEB_DIR = Path(__file__).parent / "web"
MAX_INFLIGHT = 2          # frames sent but not yet acknowledged by the client
ACK_TIMEOUT = 1.0         # seconds before assuming lost acks
MAX_TEXT = 2000


class Session:
    def __init__(self, ws: web.WebSocketResponse, backend: Backend, cfg: Config) -> None:
        self.ws = ws
        self.backend = backend
        self.cfg = cfg
        self.authed = False
        self.hwnd: int | None = None
        # settings (client adjustable)
        self.fps = 30
        self.quality = 75
        self.max_width = 0
        self.method = "screen"
        # frame pipeline state
        self.seq = 0
        self.inflight = 0
        self.ack_event = asyncio.Event()
        self.wake_event = asyncio.Event()
        self.last_crc: int | None = None
        self.last_state = ""
        self.frame_task: asyncio.Task | None = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
        # input state, released on disconnect so nothing stays stuck
        self.keys_down: dict[int, bool] = {}
        self.buttons_down: set[str] = set()

    # ------------------------------------------------------------------ io
    async def send_json(self, obj: dict) -> None:
        if not self.ws.closed:
            await self.ws.send_str(json.dumps(obj, ensure_ascii=False))

    async def run(self) -> None:
        try:
            async for msg in self.ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    if isinstance(data, dict):
                        await self.handle(data)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            await self.close()

    async def close(self) -> None:
        if self.frame_task:
            self.frame_task.cancel()
            try:
                await self.frame_task
            except (asyncio.CancelledError, Exception):
                pass
        self.release_all()
        self.pool.shutdown(wait=False)

    # ------------------------------------------------------------ handlers
    async def handle(self, m: dict) -> None:
        t = m.get("t")
        if not self.authed:
            if t == "hello" and hmac.compare_digest(str(m.get("token", "")), self.cfg.token):
                self.authed = True
                await self.send_json({
                    "t": "welcome", "version": PROTOCOL_VERSION, "agent": __version__,
                    "host": socket.gethostname(), "methods": list(self.backend.capture_methods),
                })
                await self.send_windows()
            else:
                await self.send_json({"t": "error", "code": "auth", "msg": "토큰이 올바르지 않습니다"})
                await self.ws.close()
            return

        if t == "mouse":
            self.on_mouse(m)
        elif t == "ack":
            self.inflight = max(0, self.inflight - 1)
            self.ack_event.set()
        elif t == "key":
            self.on_key(m)
        elif t == "text":
            s = str(m.get("s", ""))[:MAX_TEXT]
            if s and self.ensure_focus():
                self.backend.text(s)
        elif t == "ping":
            await self.send_json({"t": "pong", "ts": m.get("ts")})
        elif t == "list":
            await self.send_windows()
        elif t == "select":
            await self.on_select(m)
        elif t == "settings":
            self.on_settings(m)
        elif t == "release":
            self.release_all()
        elif t == "refresh":
            self.last_crc = None
            self.wake_event.set()

    async def send_windows(self) -> None:
        items = [w.to_json() for w in self.backend.list_windows() if self.cfg.is_allowed(w.exe)]
        await self.send_json({"t": "windows", "items": items})

    async def on_select(self, m: dict) -> None:
        self.release_all()
        try:
            hwnd = int(m.get("hwnd"))
        except (TypeError, ValueError):
            return
        info = self.backend.window_info(hwnd)
        if info is None or not self.cfg.is_allowed(info.exe):
            await self.send_json({"t": "error", "code": "select", "msg": "선택할 수 없는 창입니다"})
            return
        self.hwnd = hwnd
        self.last_crc = None
        self.last_state = ""
        self.inflight = 0
        self.backend.focus(hwnd)
        rect = self.backend.get_rect(hwnd)
        await self.send_json({
            "t": "selected", "hwnd": hwnd, "title": info.title, "exe": info.exe,
            "w": rect.width if rect else 0, "h": rect.height if rect else 0,
        })
        if self.frame_task is None or self.frame_task.done():
            self.frame_task = asyncio.create_task(self.frame_loop())
        self.wake_event.set()

    def on_settings(self, m: dict) -> None:
        def num(key, lo, hi, cur):
            try:
                return max(lo, min(hi, int(m.get(key, cur))))
            except (TypeError, ValueError):
                return cur
        self.fps = num("fps", 1, 60, self.fps)
        self.quality = num("quality", 10, 95, self.quality)
        self.max_width = num("maxw", 0, 7680, self.max_width)
        method = m.get("method", self.method)
        if method in CAPTURE_METHODS and method in self.backend.capture_methods:
            self.method = method
        self.last_crc = None
        self.wake_event.set()

    # --------------------------------------------------------------- input
    def ensure_focus(self) -> bool:
        return self.hwnd is not None and self.backend.focus(self.hwnd)

    def _move_to(self, m: dict) -> bool:
        if self.hwnd is None or "x" not in m or "y" not in m:
            return False
        rect = self.backend.get_rect(self.hwnd)
        if rect is None:
            return False
        try:
            x, y = norm_to_screen(float(m["x"]), float(m["y"]), rect)
        except (TypeError, ValueError):
            return False
        self.backend.mouse_move(x, y)
        return True

    def on_mouse(self, m: dict) -> None:
        if self.hwnd is None:
            return
        a = m.get("a")
        if a == "move":
            self._move_to(m)
            return
        if not self.ensure_focus():
            return
        if a in ("down", "up"):
            b = m.get("b", "left")
            if b not in MOUSE_BUTTONS:
                return
            self._move_to(m)
            down = a == "down"
            self.backend.mouse_button(b, down)
            if down:
                self.buttons_down.add(b)
            else:
                self.buttons_down.discard(b)
        elif a == "wheel":
            self._move_to(m)
            try:
                delta = max(-1200, min(1200, int(m.get("d", 0))))
            except (TypeError, ValueError):
                return
            if delta:
                self.backend.mouse_wheel(delta, bool(m.get("h")))

    def on_key(self, m: dict) -> None:
        found = keymap.lookup(str(m.get("code", "")))
        if found is None or self.hwnd is None:
            return
        vk, ext = found
        a = m.get("a")
        if a not in ("down", "up", "press"):
            return
        if a != "up" and not self.ensure_focus():
            return
        if a in ("down", "press"):
            self.backend.key(vk, True, ext)
            self.keys_down[vk] = ext
        if a in ("up", "press"):
            self.backend.key(vk, False, ext)
            self.keys_down.pop(vk, None)

    def release_all(self) -> None:
        for vk, ext in list(self.keys_down.items()):
            self.backend.key(vk, False, ext)
        self.keys_down.clear()
        for b in list(self.buttons_down):
            self.backend.mouse_button(b, False)
        self.buttons_down.clear()

    # -------------------------------------------------------------- frames
    def grab(self, hwnd: int) -> tuple[str, object]:
        """Runs in the capture thread. Returns (kind, payload)."""
        if self.backend.window_info(hwnd) is None:
            return "gone", None
        if self.backend.is_minimized(hwnd):
            return "minimized", None
        img = self.backend.capture(hwnd, self.method)
        if img is None:
            return "skip", None
        crc = zlib.crc32(img.tobytes())
        if crc == self.last_crc:
            return "same", None
        self.last_crc = crc
        size = fit_size(img.width, img.height, self.max_width)
        if size != img.size:
            img = img.resize(size, Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.quality)
        return "frame", (img.width, img.height, buf.getvalue())

    async def frame_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self.ws.closed:
            started = loop.time()
            hwnd = self.hwnd
            if hwnd is None:
                await self._wait(self.wake_event, 1.0)
                continue
            self.ack_event.clear()
            if self.inflight >= MAX_INFLIGHT:
                if not await self._wait(self.ack_event, ACK_TIMEOUT, clear=False):
                    self.inflight = 0  # acks lost; don't stall forever
                continue
            try:
                kind, payload = await loop.run_in_executor(self.pool, self.grab, hwnd)
            except Exception as exc:  # capture can fail transiently (window resizing, UAC, ...)
                log.debug("capture failed: %s", exc)
                kind, payload = "skip", None
            if hwnd != self.hwnd:
                continue
            if kind == "frame":
                w, h, jpeg = payload
                self.seq += 1
                self.inflight += 1
                await self.ws.send_bytes(pack_frame(self.seq, w, h, jpeg))
                await self._set_state("ok")
            elif kind == "gone":
                self.hwnd = None
                await self.send_json({"t": "gone", "hwnd": hwnd})
                await self.send_windows()
                continue
            elif kind == "minimized":
                await self._set_state("minimized")
            delay = 1.0 / self.fps - (loop.time() - started)
            if delay > 0:
                await self._wait(self.wake_event, delay)

    async def _set_state(self, state: str) -> None:
        if state != self.last_state:
            self.last_state = state
            await self.send_json({"t": "state", "state": state})

    @staticmethod
    async def _wait(event: asyncio.Event, timeout: float, clear: bool = True) -> bool:
        if clear:
            event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


def create_app(backend: Backend, cfg: Config) -> web.Application:
    app = web.Application()

    async def index(_request: web.Request) -> web.StreamResponse:
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20, compress=False)
        await ws.prepare(request)
        peer = request.remote
        log.info("접속: %s", peer)
        await Session(ws, backend, cfg).run()
        log.info("접속 종료: %s", peer)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", WEB_DIR)
    return app
