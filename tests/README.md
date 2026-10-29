# tests — 자동 테스트 (pytest)

하드웨어 없이도 판단 로직이 맞는지 확인합니다.

## 넣을 파일

| 파일 | 확인할 것 |
|---|---|
| `test_progress.py` | 이벤트 순서별 진행도: 읽기→20% 이하, TodoWrite→20~30%, Write→50~60%, Stop→100%, 진행도가 뒤로 가지 않음 |
| `test_state_machine.py` | Notification→INPUT, Stop→DONE, 확인 신호→SEEN, SEEN 이후 새 작업→WORK |
| `test_ack.py` | 제스처 0.9초는 확인 아님, 1초 이상은 확인. 알림 상태가 아닐 때 제스처는 무시. `BTN` 수신 시 즉시 확인 |
| `fake_serial.py` | 실제 UNO 대신 보낸 명령을 기록하는 가짜 시리얼 |

## 실행
```
cd bridge
.venv\Scripts\activate
pip install pytest
cd ..
pytest tests
```
