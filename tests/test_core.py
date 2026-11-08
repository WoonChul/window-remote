from window_remote import keymap
from window_remote.config import Config, load
from window_remote.coords import Rect, fit_size, norm_to_screen
from window_remote.protocol import pack_frame, unpack_frame


def test_norm_to_screen_corners():
    r = Rect(100, 50, 800, 600)
    assert norm_to_screen(0, 0, r) == (100, 50)
    assert norm_to_screen(0.5, 0.5, r) == (500, 350)
    # the far edge stays inside the window
    assert norm_to_screen(1, 1, r) == (899, 649)
    # out-of-range values are clamped
    assert norm_to_screen(-1, 2, r) == (100, 649)


def test_norm_to_screen_negative_monitor():
    # a window on a monitor left of the primary one
    r = Rect(-1920, 0, 1920, 1080)
    assert norm_to_screen(0.25, 0.5, r) == (-1440, 540)


def test_fit_size():
    assert fit_size(1920, 1080, 0) == (1920, 1080)
    assert fit_size(1920, 1080, 2560) == (1920, 1080)
    assert fit_size(1920, 1080, 1280) == (1280, 720)


def test_frame_roundtrip():
    data = pack_frame(7, 640, 480, b"\xff\xd8jpeg")
    assert len(data) == 9 + 6
    assert unpack_frame(data) == (7, 640, 480, b"\xff\xd8jpeg")


def test_keymap():
    assert keymap.lookup("KeyA") == (0x41, False)
    assert keymap.lookup("F1") == (0x70, False)
    assert keymap.lookup("F12") == (0x7B, False)
    assert keymap.lookup("ArrowLeft") == (0x25, True)
    assert keymap.lookup("Lang1") == (0x15, False)
    assert keymap.lookup("Nope") is None


def test_config_allowlist_and_token(tmp_path):
    path = tmp_path / "config.json"
    cfg = load(path)
    assert cfg.token and path.exists()
    assert load(path).token == cfg.token  # persisted
    assert Config(allowed_exes=[]).is_allowed("x.exe")
    c = Config(allowed_exes=["Notepad.exe"])
    assert c.is_allowed("notepad.exe") and not c.is_allowed("cmd.exe")
