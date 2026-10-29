# bridge — 중심 프로그램 (Python)

Claude Code hook 이벤트를 받아 **작업 단계·진행도를 판단**하고, UNO(LCD·RGB·부저)에 표시 명령을 보내고,
웹캠 제스처·빵판 버튼으로 **확인**을 받고, 기록을 저장하고, 대시보드에 실시간으로 알려줍니다.

## 실행

```
cd bridge
pip install -r requirements.txt
python main.py              # 또는 start_bridge.bat 더블클릭
```

| 옵션 | 의미 |
|---|---|
| `--port COM3` | UNO 포트 변경 (기본 COM5) |
| `--fake-serial` | UNO 없이 실행, 보낼 명령을 화면에 출력 |
| `--no-gesture` | 웹캠 제스처 끄기 (버튼만 사용) |

- bridge가 COM5를 쓰는 동안에는 아두이노 시리얼 모니터·`serial_test.py`·`gesture_ack_test.py`를 함께 열 수 없습니다.
- 실행하면 대시보드(`http://127.0.0.1:8000`)가 자동으로 열립니다. 열지 않으려면 `--no-browser`

## 파일

| 파일 | 역할 |
|---|---|
| `main.py` | 실행 시작점. 아래 모듈을 띄우고 서버 실행 |
| `config.py` | COM 포트, 알림 기준 시간, 제스처 설정 (환경 변수로 변경 가능) |
| `progress.py` | 도구 이름 → 단계·진행도 계산 |
| `state_machine.py` | 상태 전이(IDLE·WORK·INPUT·DONE·SEEN)와 UNO 명령 생성 |
| `serial_link.py` | UNO 연결, 명령이 바뀔 때만 전송, 끊기면 자동 재연결, `BTN` 수신 |
| `server.py` | FastAPI: hook 수신, 대시보드 API·WebSocket (아래 표) |
| `storage.py` | SQLite 기록 (`data/notifier.db`), 오늘 요약 |
| `system_monitor.py` | CPU 사용량·온도, 메모리, 배터리 (2초마다, 최근 10분) |
| `esp32_link.py` | ESP32-S3 하트비트 수신·연결 상태 |
| `lan.py` | 이 PC의 Wi-Fi 주소 찾기, ESP32-S3 자동 찾기용 UDP 신호 |
| `presence/gesture.py` | 학습한 YOLO 분류 모델로 `ok` 제스처 판단 (사용자 작성) |
| `presence/gesture_watch.py` | **알림이 울리는 동안에만** 웹캠을 켜고 제스처를 찾는 스레드 |
| `tools/serial_test.py` | UNO 단독 시험 |
| `tools/gesture_ack_test.py` | 제스처로 부저 멈추기 단독 시험 |
| `tools/hook_sim.py` | Claude Code 없이 hook 이벤트를 흉내 내어 전체 연동 시험 |
| `tools/esp32_sim.py` | ESP32-S3 없이 하트비트 시험 (시뮬레이션 표시) |
| `start_bridge.bat` | 더블클릭 실행 |

## API

| 주소 | 내용 |
|---|---|
| `POST /event` | Claude Code hook 이벤트 (hooks/send_event.py가 보냄) |
| `GET /api/state` · `WS /ws` | 대시보드 전체 상태 (AI·컴퓨터·UNO·웹캠·ESP32) |
| `GET /api/system/history` | 최근 10분 CPU·온도·메모리 |
| `GET /api/tasks` · `GET /api/stats` | 최근 작업 · 오늘 요약 |
| `GET /api/camera.jpg` | 웹캠 최신 1장 (알림·미리보기 중에만, 저장 안 함) |
| `POST/DELETE /api/camera/preview` | 카메라 미리보기 켜기(최대 60초)/끄기 |
| `POST /api/ack` | 원격으로 부저 끄기 (`{"method": "dashboard"|"phone"|"esp32"}`) |
| `GET /api/access` | PC에서 보는지 여부, (PC에서만) 휴대폰 접속 주소·토큰 |
| `POST /api/esp32/heartbeat` · `GET /api/esp32` | ESP32-S3 상태 보내기 + AI 상태 받기 |

## 같은 Wi-Fi 공개 (기본 켜짐)
- 휴대폰·ESP32-S3 등 **다른 기기는 접속 토큰이 있어야** 합니다. 토큰은 처음 실행 때 만들어져 `data/access_token.txt`에 저장되고 bridge 창에 표시됩니다.
- 다른 기기에서 막는 것: Claude Code hook 입력(`/event`), 웹캠 화면·미리보기
- ESP32-S3가 PC를 자동으로 찾도록 2초마다 UDP 47800으로 신호를 보냅니다 (`lan.py`, 토큰 미포함)
- 이 PC에서만 쓰려면: `set NOTIFIER_LAN=0` 후 실행
- 처음 실행 때 Windows 방화벽 창 → **개인 네트워크 허용**

## 진행도 규칙 (`progress.py`)

| 단계 (LCD 1줄) | 판단 근거 | 진행도 |
|---|---|---|
| `READING` | 요청 직후, `Read`·`Grep`·`Glob`·`WebFetch`·`WebSearch`, 수정 전 `Bash` | 0–20% |
| `PLANNING` | `TodoWrite`·`TaskCreate`·`TaskUpdate`·`EnterPlanMode` | 20–30% |
| `BUILDING` | `Write`·`Edit`·`MultiEdit`·`NotebookEdit`, 수정 후 일반 `Bash` | 50–60% |
| `REVIEWING` | 수정 후 테스트·빌드·검사 명령 (`pytest`, `npm test`, `tsc`, `git diff` …) | 80–90% |

LCD 표시 예: `BUILDING   03:12` / `██████______ 54%` (단계 + 경과 시간 / 진행 막대)

- 단계는 앞으로만 갑니다. 단계 안에서는 시간이 지나며 상한에 천천히 다가갑니다.
- `Agent`·MCP 도구처럼 판단하기 어려운 도구는 현재 단계를 유지합니다.

## 알림 규칙 (`state_machine.py`)

| 상황 | 동작 |
|---|---|
| `Stop` (응답 끝) — 작업이 **20초 이상** | DONE 알림 (초록 + 도-미-솔), LCD `TOOK 03:12` |
| `Stop` — 20초 미만 (짧은 대답) | 소리 없이 IDLE, LCD `LAST OK 00:05` |
| 권한 요청(`Notification`), `AskUserQuestion`, `ExitPlanMode` | **10초** 안에 답하지 않으면 INPUT 알림 (주황 + 띵-동) |
| 10초 안에 승인·답변 | 알림 취소 (자리에 있을 때 방해하지 않음) |
| "입력 기다리는 중" 알림 (idle) | 무시 (완료 알림을 이미 냈으므로) |
| 제스처 1초 유지 / 빵판 버튼 | SEEN (소리 정지), 확인 방법·걸린 시간 기록 |
| 확인 없이 Claude에서 바로 답함 | 작업 중으로 복귀, 확인 방법 `answered`로 기록 |

기준 시간은 `config.py` 또는 환경 변수로 바꿀 수 있습니다: `NOTIFIER_MIN_ALERT`, `NOTIFIER_INPUT_DELAY`.

### 알려진 한계
- 진행도는 **추정값**입니다. Claude가 실제로 몇 %를 했는지는 알 수 없습니다.
- 권한을 승인한 뒤 그 명령이 10초 넘게 실행되면, 승인 신호가 명령이 끝날 때 와서 답변 대기 알림이 잘못 울릴 수 있습니다(제스처·버튼으로 끄면 됨).
- 여러 Claude Code 세션을 동시에 돌리면 가장 최근 이벤트를 보낸 세션 기준으로 표시됩니다.
