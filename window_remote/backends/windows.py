"""Windows backend using only ctypes (user32 / gdi32 / dwmapi / kernel32).

- Coordinates are physical pixels: the process is made Per-Monitor DPI aware.
- "screen" capture copies the window's area from the desktop (fast, but the
  window must be visible on top). "window" capture uses PrintWindow, which
  also works when the window is covered by others (slower, some GPU apps
  draw black).
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from PIL import Image

from ..coords import Rect
from .base import Backend, WindowInfo

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

HWND = wintypes.HWND
HDC = wintypes.HDC
ULONG_PTR = ctypes.c_size_t

# --- constants -------------------------------------------------------------
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SW_RESTORE = 9
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004
MAPVK_VK_TO_VSC = 0

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


# --- structures --------------------------------------------------------------
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)


def _sig(fn, argtypes, restype=wintypes.BOOL):
    fn.argtypes = argtypes
    fn.restype = restype


_sig(user32.EnumWindows, [WNDENUMPROC, wintypes.LPARAM])
_sig(user32.IsWindow, [HWND])
_sig(user32.IsWindowVisible, [HWND])
_sig(user32.IsIconic, [HWND])
_sig(user32.GetWindow, [HWND, wintypes.UINT], HWND)
_sig(user32.GetWindowLongW, [HWND, ctypes.c_int], wintypes.LONG)
_sig(user32.GetWindowTextLengthW, [HWND], ctypes.c_int)
_sig(user32.GetWindowTextW, [HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.GetWindowThreadProcessId, [HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD)
_sig(user32.GetWindowRect, [HWND, ctypes.POINTER(wintypes.RECT)])
_sig(user32.GetForegroundWindow, [], HWND)
_sig(user32.SetForegroundWindow, [HWND])
_sig(user32.BringWindowToTop, [HWND])
_sig(user32.ShowWindow, [HWND, ctypes.c_int])
_sig(user32.AttachThreadInput, [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL])
_sig(user32.GetSystemMetrics, [ctypes.c_int], ctypes.c_int)
_sig(user32.SetCursorPos, [ctypes.c_int, ctypes.c_int])
_sig(user32.SendInput, [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int], wintypes.UINT)
_sig(user32.MapVirtualKeyW, [wintypes.UINT, wintypes.UINT], wintypes.UINT)
_sig(user32.GetDC, [HWND], HDC)
_sig(user32.GetWindowDC, [HWND], HDC)
_sig(user32.ReleaseDC, [HWND, HDC], ctypes.c_int)
_sig(user32.PrintWindow, [HWND, HDC, wintypes.UINT])
_sig(kernel32.GetCurrentThreadId, [], wintypes.DWORD)
_sig(kernel32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE)
_sig(kernel32.QueryFullProcessImageNameW,
     [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)])
_sig(kernel32.CloseHandle, [wintypes.HANDLE])
_sig(gdi32.CreateCompatibleDC, [HDC], HDC)
_sig(gdi32.CreateCompatibleBitmap, [HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP)
_sig(gdi32.SelectObject, [HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ)
_sig(gdi32.DeleteObject, [wintypes.HGDIOBJ])
_sig(gdi32.DeleteDC, [HDC])
_sig(gdi32.BitBlt, [HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD])
_sig(gdi32.GetDIBits, [HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                       ctypes.POINTER(BITMAPINFO), wintypes.UINT], ctypes.c_int)
_sig(dwmapi.DwmGetWindowAttribute, [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD],
     ctypes.c_long)


def enable_dpi_awareness() -> None:
    """Make every coordinate a physical pixel, even at 125% / 150% scaling."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except AttributeError:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass


def _hwnd(h) -> int:
    return int(h or 0)


class WindowsBackend(Backend):
    name = "windows"
    capture_methods = ("screen", "window")

    def __init__(self) -> None:
        enable_dpi_awareness()
        self._own_pid = os.getpid()
        self._lock = threading.Lock()

    # --- window queries --------------------------------------------------
    def _title(self, hwnd: int) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _pid(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _exe(self, pid: int) -> str:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            kernel32.CloseHandle(h)

    def _is_cloaked(self, hwnd: int) -> bool:
        cloaked = wintypes.DWORD()
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                           ctypes.sizeof(cloaked))
        return res == 0 and cloaked.value != 0

    def _is_app_window(self, hwnd: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return False
        if user32.GetWindow(hwnd, GW_OWNER):
            return False
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return False
        if self._is_cloaked(hwnd):
            return False
        return user32.GetWindowTextLengthW(hwnd) > 0

    def list_windows(self) -> list[WindowInfo]:
        handles: list[int] = []

        @WNDENUMPROC
        def cb(h, _lparam):
            handles.append(_hwnd(h))
            return True

        user32.EnumWindows(cb, 0)
        result = []
        for h in handles:
            if not self._is_app_window(h):
                continue
            info = self.window_info(h)
            if info and info.pid != self._own_pid:
                result.append(info)
        return result

    def window_info(self, hwnd: int) -> WindowInfo | None:
        if not user32.IsWindow(hwnd):
            return None
        pid = self._pid(hwnd)
        return WindowInfo(hwnd=hwnd, title=self._title(hwnd), exe=self._exe(pid), pid=pid)

    def get_rect(self, hwnd: int) -> Rect | None:
        r = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                        ctypes.sizeof(r)) != 0:
            if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
                return None
        rect = Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)
        return None if rect.is_empty() else rect

    def is_minimized(self, hwnd: int) -> bool:
        return bool(user32.IsIconic(hwnd))

    def focus(self, hwnd: int) -> bool:
        if not user32.IsWindow(hwnd):
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg = _hwnd(user32.GetForegroundWindow())
        if fg == hwnd:
            return True
        # Windows blocks SetForegroundWindow from background processes; attaching
        # to the current foreground thread's input queue lifts that restriction.
        cur_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(fg_tid and fg_tid != cur_tid and user32.AttachThreadInput(cur_tid, fg_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
        return _hwnd(user32.GetForegroundWindow()) == hwnd

    # --- capture ---------------------------------------------------------
    @staticmethod
    def _read_bitmap(dc, bmp, w: int, h: int) -> Image.Image:
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down rows
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        if gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS) == 0:
            raise OSError("GetDIBits failed")
        return Image.frombytes("RGB", (w, h), buf.raw, "raw", "BGRX")

    def _grab_screen(self, rect: Rect) -> Image.Image:
        screen_dc = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen_dc)
        bmp = gdi32.CreateCompatibleBitmap(screen_dc, rect.width, rect.height)
        old = gdi32.SelectObject(mem, bmp)
        try:
            gdi32.BitBlt(mem, 0, 0, rect.width, rect.height, screen_dc, rect.left, rect.top, SRCCOPY)
            gdi32.SelectObject(mem, old)
            return self._read_bitmap(mem, bmp, rect.width, rect.height)
        finally:
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen_dc)

    def _grab_window(self, hwnd: int, rect: Rect) -> Image.Image | None:
        wr = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
            return None
        w, h = wr.right - wr.left, wr.bottom - wr.top
        if w <= 0 or h <= 0:
            return None
        win_dc = user32.GetWindowDC(hwnd)
        mem = gdi32.CreateCompatibleDC(win_dc)
        bmp = gdi32.CreateCompatibleBitmap(win_dc, w, h)
        old = gdi32.SelectObject(mem, bmp)
        try:
            user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
            gdi32.SelectObject(mem, old)
            img = self._read_bitmap(mem, bmp, w, h)
        finally:
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(hwnd, win_dc)
        # GetWindowRect includes invisible resize borders; crop to visible bounds
        # so input coordinates match what the client sees.
        ox, oy = rect.left - wr.left, rect.top - wr.top
        return img.crop((ox, oy, ox + rect.width, oy + rect.height))

    def capture(self, hwnd: int, method: str) -> Image.Image | None:
        rect = self.get_rect(hwnd)
        if rect is None:
            return None
        if method == "window":
            return self._grab_window(hwnd, rect)
        return self._grab_screen(rect)

    # --- input -------------------------------------------------------------
    @staticmethod
    def _send(*inputs: INPUT) -> None:
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    @staticmethod
    def _mouse_input(flags: int, data: int = 0) -> INPUT:
        return INPUT(type=INPUT_MOUSE,
                     u=_INPUTUNION(mi=MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)))

    @staticmethod
    def _key_input(vk: int, scan: int, flags: int) -> INPUT:
        return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))

    def mouse_move(self, x: int, y: int) -> None:
        # SetCursorPos lands on the exact pixel (SendInput's 0-65535 absolute
        # scale can be off by one on large desktops).
        user32.SetCursorPos(int(x), int(y))

    def mouse_button(self, button: str, down: bool) -> None:
        flags = BUTTON_FLAGS.get(button)
        if flags:
            self._send(self._mouse_input(flags[0] if down else flags[1]))

    def mouse_wheel(self, delta: int, horizontal: bool = False) -> None:
        flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
        self._send(self._mouse_input(flag, int(delta)))

    def key(self, vk: int, down: bool, extended: bool = False) -> None:
        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF
        flags = (0 if down else KEYEVENTF_KEYUP) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
        self._send(self._key_input(vk, scan, flags))

    def text(self, s: str) -> None:
        data = s.encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        inputs = []
        for u in units:
            inputs.append(self._key_input(0, u, KEYEVENTF_UNICODE))
            inputs.append(self._key_input(0, u, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        if inputs:
            self._send(*inputs)
