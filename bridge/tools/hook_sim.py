"""Claude Code 없이 연동 시험: 실제 hook과 같은 JSON을 send_event.py에 넣어 bridge로 보냄

사용법 (bridge가 켜진 상태에서, 다른 터미널):
    python bridge/tools/hook_sim.py          # 약 50초, 실제 알림 규칙 그대로
    python bridge/tools/hook_sim.py --fast   # 대기 시간 1/5 (bridge도 짧은 기준으로 켰을 때)

순서: 요청 → 읽기 → 계획 → 수정 → 테스트 → 권한 요청(답변 대기 알림) → 승인 → 완료 알림
알림 단계에서 'ok' 제스처나 빵판 버튼으로 꺼 보세요.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

SEND = Path(__file__).resolve().parents[2] / "hooks" / "send_event.py"
FAST = "--fast" in sys.argv
SESSION = "sim-" + time.strftime("%H%M%S")

STEPS = [
    # (이벤트, 추가 필드, 대기초, 기대 결과)
    ("UserPromptSubmit", {"prompt": "(시험)"}, 3, "LCD: READING 0% · 파랑 숨쉬기"),
    ("PreToolUse", {"tool_name": "Read"}, 2, "READING"),
    ("PreToolUse", {"tool_name": "Grep"}, 3, "READING (조금씩 증가)"),
    ("PreToolUse", {"tool_name": "TodoWrite"}, 4, "PLANNING 20%대"),
    ("PreToolUse", {"tool_name": "Edit"}, 3, "BUILDING 50%대 · 청록"),
    ("PreToolUse", {"tool_name": "Write"}, 3, "BUILDING"),
    ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "python -m pytest -q"}}, 3,
     "REVIEWING 80%대 · 초록빛"),
    ("Notification", {"message": "Claude needs your permission to use Bash",
                      "notification_type": "permission_prompt"}, 15,
     "10초 뒤 답변 대기: 주황 깜빡임 + 띵-동 → 제스처/버튼으로 꺼 보기"),
    ("PostToolUse", {"tool_name": "Bash"}, 4, "승인됨 → 다시 REVIEWING"),
    ("Stop", {"stop_hook_active": False}, 0, "완료: 초록 + 도-미-솔, LCD 'TOOK 00:40'대 → 제스처/버튼으로 꺼 보기"),
]


def send(event: str, extra: dict) -> None:
    payload = {"session_id": SESSION, "cwd": str(Path.cwd()), "hook_event_name": event, **extra}
    subprocess.run([sys.executable, str(SEND), event], input=json.dumps(payload).encode(), timeout=5)


def main() -> None:
    t0 = time.monotonic()
    for event, extra, wait, expect in STEPS:
        tool = extra.get("tool_name", "")
        print(f"[{time.monotonic() - t0:5.1f}s] {event} {tool}\n         기대: {expect}")
        send(event, extra)
        time.sleep(wait / 5 if FAST else wait)
    print("\n끝. bridge 창의 로그와 data/hook_log.jsonl 에 기록이 남았는지 확인하세요.")


if __name__ == "__main__":
    main()
