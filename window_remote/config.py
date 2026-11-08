"""Agent configuration stored in the user's profile."""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_PORT = 8765


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "window-remote"


@dataclass
class Config:
    token: str = ""
    port: int = DEFAULT_PORT
    # Executable names (e.g. "notepad.exe") that may be controlled. Empty = all.
    allowed_exes: list[str] = field(default_factory=list)

    def is_allowed(self, exe: str) -> bool:
        if not self.allowed_exes:
            return True
        return exe.lower() in {e.lower() for e in self.allowed_exes}


def new_token() -> str:
    return secrets.token_urlsafe(16)


def load(path: Path | None = None) -> Config:
    path = path or config_dir() / "config.json"
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = Config(
                token=str(data.get("token", "")),
                port=int(data.get("port", DEFAULT_PORT)),
                allowed_exes=[str(e) for e in data.get("allowed_exes", [])],
            )
        except (ValueError, OSError) as exc:
            print(f"[경고] 설정 파일을 읽지 못해 기본값을 씁니다: {exc}")
    if not cfg.token:
        cfg.token = new_token()
        save(cfg, path)
    return cfg


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
