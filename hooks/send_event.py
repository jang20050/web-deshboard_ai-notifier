"""Claude Code hook → bridge 전달 (표준 라이브러리만 사용)

Claude Code가 hook 이벤트마다 이 스크립트를 실행하고, 이벤트 정보를 JSON으로 표준 입력에 넣어 줍니다.
필요한 항목만 골라 bridge(http://127.0.0.1:8000/event)로 보냅니다.

- bridge가 꺼져 있어도 0.7초 안에 조용히 끝나서 Claude Code 작업을 막지 않습니다(항상 종료 코드 0).
- 프롬프트·파일 내용은 보내지 않습니다. Bash 명령은 '검토 단계' 판단용으로 앞 120자만 보냅니다.
- 연동 확인용으로 data/hook_log.jsonl 에 받은 이벤트 요약을 남깁니다(LOG = False 로 끌 수 있음).
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

URL = os.environ.get("NOTIFIER_URL", "http://127.0.0.1:8000/event")
LOG = True
LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "hook_log.jsonl"
LOG_MAX_BYTES = 1_000_000


def read_input() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def summarize(data: dict, fallback_event: str) -> dict:
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    command = tool_input.get("command")
    cwd = data.get("cwd") or ""
    return {
        "event": data.get("hook_event_name") or fallback_event,
        "tool": data.get("tool_name"),
        "session": data.get("session_id"),
        "project": Path(cwd).name if cwd else None,
        "command": command[:120] if isinstance(command, str) else None,
        "message": (data.get("message") or "")[:200] or None,
        "notification_type": data.get("notification_type"),
        "ts": time.time(),
    }


def write_log(evt: dict, data: dict, sent: str) -> None:
    if not LOG:
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".old.jsonl"))
        row = {**evt, "keys": sorted(data.keys()), "sent": sent}
        row.pop("command", None)  # 로그에는 명령 내용도 남기지 않음
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main() -> None:
    data = read_input()
    evt = summarize(data, sys.argv[1] if len(sys.argv) > 1 else "")
    sent = "ok"
    try:
        req = urllib.request.Request(URL, data=json.dumps(evt).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        # 시스템 프록시 설정을 거치지 않고 이 PC의 bridge로 바로 보냄
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open(req, timeout=0.7).read()
    except Exception as e:
        sent = f"fail: {type(e).__name__}"
    write_log(evt, data, sent)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
