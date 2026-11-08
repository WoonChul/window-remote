"""Entry point: python -m window_remote"""

from __future__ import annotations

import argparse
import logging
import socket

from aiohttp import web

from . import __version__, backends, config


def lan_addresses() -> list[str]:
    addrs: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:  # the address used for the default route
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


def main() -> None:
    p = argparse.ArgumentParser(prog="window-remote", description="선택한 프로그램 창을 원격으로 제어하는 에이전트")
    p.add_argument("--host", default="0.0.0.0", help="수신 주소 (기본 0.0.0.0)")
    p.add_argument("--port", type=int, help=f"포트 (기본 {config.DEFAULT_PORT})")
    p.add_argument("--mock", action="store_true", help="가짜 창으로 실행 (개발·테스트용)")
    p.add_argument("--new-token", action="store_true", help="접속 토큰을 새로 만든다")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    cfg = config.load()
    if args.new_token:
        cfg.token = config.new_token()
        config.save(cfg)
    port = args.port or cfg.port

    backend = backends.create(mock=args.mock)

    from .server import create_app
    app = create_app(backend, cfg)

    print(f"window-remote {__version__}  ({backend.name})")
    print("같은 네트워크의 폰·PC 브라우저에서 아래 주소로 접속하세요:")
    for addr in lan_addresses() or ["127.0.0.1"]:
        print(f"  http://{addr}:{port}/?token={cfg.token}")
    print(f"설정 파일: {config.config_dir() / 'config.json'}")
    print("종료: Ctrl+C")
    web.run_app(app, host=args.host, port=port, print=None)


if __name__ == "__main__":
    main()
