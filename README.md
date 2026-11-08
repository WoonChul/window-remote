# window-remote

Windows PC에서 실행 중인 **프로그램 창 하나를 골라서** 폰·태블릿·다른 PC로 빠르고 정밀하게 제어하는 오픈소스 도구입니다.
화면 전체를 보내는 일반 원격 데스크톱과 달리, 선택한 창만 보내고 그 창에만 입력합니다.

> 현재 단계: **MVP (0.1)** — 같은 네트워크(LAN) 안에서 웹 브라우저로 제어. 외부 접속·설치 파일은 다음 단계입니다.

## 기능

- 실행 중인 창 목록에서 제어할 창 선택
- 선택한 창만 캡처해서 전송 (바뀐 화면만 보냄, 응답 대기 중인 프레임은 최대 2개)
- 마우스: 클릭, 드래그, 휠, 우클릭 / 키보드: 모든 키, 단축키, 한글 직접 입력
- 정밀 제어
  - 정확한 픽셀 위치로 이동 (화면 배율 125%/150%에서도 일치)
  - 확대(핀치·Ctrl+휠) 상태에서 클릭
  - **트랙패드 모드**: 화면을 터치패드처럼 써서 커서를 조금씩 이동. 확대할수록 더 미세하게 움직임
  - 더블탭은 같은 위치로 보정되어 더블클릭으로 인식
- 폰용 키 막대: Ctrl/Alt/Shift/Win(누른 상태 유지), Esc, Tab, 방향키, 한/영, Ctrl+Z/C/V/S
- 연결이 끊기면 눌린 키·버튼을 자동으로 해제

## 받기

저장소: https://github.com/WoonChul/window-remote

```powershell
git clone https://github.com/WoonChul/window-remote.git C:\window-remote
```

git이 없으면 GitHub 페이지의 **Code → Download ZIP**으로 받아서 `C:\window-remote`에 푸세요.

## 실행 (호스트 Windows PC)

Python 3.10 이상이 필요합니다. 폴더(`C:\window-remote`)에서 배치 파일을 더블클릭하면 됩니다.

| 파일 | 하는 일 |
| --- | --- |
| `setup.bat` | 가상환경(`.venv`)을 만들고 필요한 패키지 설치. 처음 한 번만 |
| `run.bat` | 에이전트 실행 (설치가 안 돼 있으면 `setup.bat`부터 실행) |
| `run-admin.bat` | 관리자 권한으로 실행. 관리자 권한 프로그램을 제어할 때 |
| `test.bat` | 테스트 실행 |

명령 프롬프트에서 직접 실행하려면:

```powershell
cd C:\window-remote
setup.bat
run.bat --port 9000      # 옵션은 그대로 전달됨
```

실행하면 접속 주소가 표시됩니다.

```
window-remote 0.1.0  (windows)
같은 네트워크의 폰·PC 브라우저에서 아래 주소로 접속하세요:
  http://192.168.0.10:8765/?token=xxxxxxxx
```

처음 실행할 때 Windows 방화벽 창이 뜨면 **개인 네트워크**를 허용하세요.

### 옵션

| 옵션 | 설명 |
| --- | --- |
| `--port 9000` | 포트 변경 (기본 8765) |
| `--new-token` | 접속 토큰 새로 만들기 (기존 기기는 다시 접속 필요) |
| `--mock` | 가짜 창으로 실행 (Windows가 아니어도 개발·테스트 가능) |
| `-v` | 자세한 로그 |

### 설정 파일

`%APPDATA%\window-remote\config.json`

```json
{
  "token": "자동 생성",
  "port": 8765,
  "allowed_exes": ["notepad.exe", "CAMMaster.exe"]
}
```

`allowed_exes`가 비어 있으면 모든 창을 제어할 수 있습니다. 목록을 넣으면 그 프로그램들만 보이고 제어됩니다.

## 사용법 (클라이언트)

| 동작 | PC (마우스) | 폰·태블릿 (포인터 모드) | 폰·태블릿 (트랙패드 모드) |
| --- | --- | --- | --- |
| 클릭 | 클릭 | 탭 | 탭 (커서 위치) |
| 우클릭 | 우클릭 | 길게 누르기 | 두 손가락 탭 |
| 드래그 | 드래그 | 누른 채 이동 | 길게 누른 뒤 이동 |
| 스크롤 | 휠 | — | 두 손가락 위아래 |
| 확대/이동 | Ctrl+휠 | 두 손가락 핀치·이동 | 툴바 −/맞춤/+ |
| 키 입력 | 화면을 클릭한 뒤 그대로 입력 | ⌨ 버튼 → 입력칸 | ⌨ 버튼 → 입력칸 |

### 캡처 방식 (⚙ 설정)

- **화면** (기본): 빠름. 제어할 창이 다른 창에 가려지지 않아야 합니다. 입력할 때 창을 자동으로 앞으로 가져옵니다.
- **창**: 다른 창에 가려져도 캡처됩니다. 조금 느리고, 일부 GPU 가속 프로그램은 검게 나올 수 있습니다.

## 알려진 제한

- 잠금 화면, 로그아웃 상태, UAC 확인 창은 제어할 수 없습니다. 호스트 PC는 로그인된 상태여야 합니다.
- 관리자 권한으로 실행된 프로그램을 제어하려면 에이전트도 관리자 권한으로 실행해야 합니다.
- 현재는 LAN 안에서 암호화되지 않은 HTTP로 통신합니다. 신뢰할 수 있는 네트워크에서만 쓰세요. (외부 접속과 암호화는 다음 단계에서 지원)
- RDP로 접속했다가 끊으면 세션이 잠겨 동작하지 않습니다.

## 개발

개발 환경: `C:\window-remote` (Windows, cloud PC)

```powershell
setup.bat                  # .venv 생성 + 개발용 패키지 설치
test.bat                   # 테스트
run.bat --mock -v          # 가짜 창으로 웹 클라이언트만 개발할 때
```

Linux/macOS에서도 `pip install -e ".[dev]"`, `pytest`, `python -m window_remote --mock`으로 개발할 수 있습니다.

구조:

```
window_remote/
  __main__.py      실행 진입점
  server.py        HTTP/WebSocket 서버, 세션(창 선택·프레임 전송·입력 처리)
  protocol.py      메시지 형식 (docs/protocol.md)
  coords.py        좌표 변환
  keymap.py        브라우저 키 코드 → Windows 가상 키
  config.py        설정 파일
  backends/
    windows.py     Windows API (ctypes): 창 목록, 캡처, SendInput
    mock.py        테스트용 가짜 백엔드
  web/             웹 클라이언트 (빌드 없음)
```

## 로드맵

1. ✅ 에이전트 기본 (창 목록·캡처·입력)
2. ✅ LAN 웹 클라이언트 MVP
3. 🔶 정밀 제어 (줌·트랙패드 완료 / 매크로 버튼, UI Automation 요소 조작 예정)
4. 지연 측정·고속화 (Windows Graphics Capture, H.264)
5. 외부 연결 (중개 서버 + WebRTC P2P, 페어링)
6. 보안·권한 (승인, 제어 중 표시, 접속 기록)
7. 설치 파일·자동 업데이트·코드 서명
8. 베타 테스트, 안드로이드 앱

## 라이선스

[MIT](LICENSE)
