# 프로토콜 (버전 1)

클라이언트는 `ws://<호스트>:<포트>/ws`에 WebSocket으로 접속합니다.
제어 메시지는 JSON 텍스트, 화면은 바이너리입니다. 이 문서를 지키면 어떤 언어로 클라이언트를 만들어도 됩니다.

## 좌표

마우스 좌표 `x`, `y`는 **선택한 창 기준 0.0 ~ 1.0 비율**입니다. (0,0) = 창 왼쪽 위, (1,1) = 오른쪽 아래.
에이전트가 프레임을 축소해서 보내도, 비율로 보내면 호스트의 정확한 픽셀로 변환됩니다.

## 클라이언트 → 에이전트 (JSON)

| `t` | 필드 | 설명 |
| --- | --- | --- |
| `hello` | `token` | 첫 메시지. 토큰이 틀리면 `error`(code `auth`) 후 연결 종료 |
| `list` | | 창 목록 요청 → `windows` |
| `select` | `hwnd` | 제어할 창 선택 → `selected`, 이후 프레임 전송 시작 |
| `settings` | `fps`(1-60), `quality`(10-95), `maxw`(0=원본), `method`(`screen`/`window`) | 전송 설정 |
| `mouse` | `a`: `move`/`down`/`up`/`wheel`, `x`, `y`, `b`: `left`/`right`/`middle`, `d`: 휠 값(±120 = 한 칸), `h`: 가로 휠 | 마우스 |
| `key` | `a`: `down`/`up`/`press`, `code` | 키. `code`는 브라우저 `KeyboardEvent.code` (예: `KeyA`, `Enter`, `ControlLeft`, `Lang1`) |
| `text` | `s` | 유니코드 문자열 직접 입력 (한글 포함, 최대 2000자) |
| `ack` | `seq` | 프레임을 화면에 그린 뒤 반드시 보냄 (흐름 제어) |
| `ping` | `ts` | → `pong` (같은 `ts`) 왕복 지연 측정 |
| `release` | | 눌린 키·버튼 모두 해제 |
| `refresh` | | 화면이 안 바뀌어도 다음 프레임 강제 전송 |

## 에이전트 → 클라이언트 (JSON)

| `t` | 필드 |
| --- | --- |
| `welcome` | `version`, `agent`, `host`, `methods` |
| `windows` | `items`: `[{hwnd, title, exe, pid}]` |
| `selected` | `hwnd`, `title`, `exe`, `w`, `h` |
| `state` | `state`: `ok` / `minimized` |
| `gone` | `hwnd` (창이 닫힘) |
| `pong` | `ts` |
| `error` | `code`, `msg` |

## 에이전트 → 클라이언트 (바이너리: 프레임)

리틀 엔디언, 9바이트 헤더 + JPEG.

| 오프셋 | 크기 | 내용 |
| --- | --- | --- |
| 0 | u8 | 메시지 종류 (1 = 프레임) |
| 1 | u32 | 순번 `seq` |
| 5 | u16 | 프레임 폭 |
| 7 | u16 | 프레임 높이 |
| 9 | … | JPEG 데이터 |

## 흐름 제어

에이전트는 `ack`를 받지 못한 프레임이 2개가 되면 전송을 멈춥니다. 네트워크가 느려도 오래된 화면이 쌓이지 않고 항상 최신 화면을 보내기 위해서입니다. 화면이 바뀌지 않으면 프레임을 보내지 않습니다.
