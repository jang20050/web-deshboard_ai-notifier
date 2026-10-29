"""Claude Code 사용자 설정(~/.claude/settings.json)에 알림 장치 hook을 등록·해제

    python hooks/install_hooks.py            # 등록 (기존 설정은 백업 후 합침)
    python hooks/install_hooks.py --remove   # 해제
    python hooks/install_hooks.py --print    # 바꾸지 않고 들어갈 내용만 출력

- 다른 hook 설정은 건드리지 않고, 이 프로젝트의 send_event.py 항목만 넣고 뺍니다(여러 번 실행해도 중복 없음).
- 변경 전 settings.json 을 settings.json.bak-날짜시간 으로 백업합니다.
- 등록 후에는 Claude Code(데스크톱)에서 **새 세션**을 시작해야 적용됩니다.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
SCRIPT = Path(__file__).resolve().parent / "send_event.py"
MARK = "send_event.py"

# 이벤트 → matcher (None이면 matcher 없음)
EVENTS = {
    "UserPromptSubmit": None,
    "PreToolUse": "*",
    "PostToolUse": "*",
    "Notification": None,
    "Stop": None,
    "SessionEnd": None,
}


def command_for(event: str) -> str:
    # 경로에 공백·한글이 있어 큰따옴표로 감싸고, cmd·Git Bash 모두에서 동작하도록 / 를 사용
    py = Path(sys.executable).as_posix()
    return f'"{py}" "{SCRIPT.as_posix()}" {event}'


def our_group(event: str) -> dict:
    group = {"hooks": [{"type": "command", "command": command_for(event), "timeout": 5}]}
    if EVENTS[event] is not None:
        group = {"matcher": EVENTS[event], **group}
    return group


def strip_ours(hooks: dict) -> dict:
    out = {}
    for event, groups in hooks.items():
        kept = [g for g in groups
                if not any(MARK in (h.get("command") or "") for h in g.get("hooks", []))]
        if kept:
            out[event] = kept
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()

    if args.print:
        print(json.dumps({"hooks": {e: [our_group(e)] for e in EVENTS}}, indent=2, ensure_ascii=False))
        return

    settings = {}
    if SETTINGS.exists():
        try:
            settings = json.loads(SETTINGS.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            print(f"{SETTINGS} 의 JSON 형식이 잘못되어 수정하지 않았습니다: {e}")
            sys.exit(1)
        backup = SETTINGS.with_name(f"settings.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(SETTINGS, backup)
        print(f"백업: {backup}")

    hooks = strip_ours(settings.get("hooks", {}))
    if not args.remove:
        for event in EVENTS:
            hooks.setdefault(event, []).append(our_group(event))
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.remove:
        print(f"해제 완료: {SETTINGS}")
    else:
        print(f"등록 완료: {SETTINGS}")
        print(f"  이벤트: {', '.join(EVENTS)}")
        print(f"  실행 명령 예: {command_for('Stop')}")
        print("Claude Code 데스크톱에서 새 세션을 시작하면 적용됩니다.")


if __name__ == "__main__":
    main()
