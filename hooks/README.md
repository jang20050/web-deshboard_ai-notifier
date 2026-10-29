# hooks — Claude Code 연동

Claude Code(데스크톱 앱의 Code 포함)는 작업 중 특정 시점(hook 이벤트)에 지정한 명령을 실행합니다.
`send_event.py`가 그 이벤트 정보를 bridge(`http://127.0.0.1:8000/event`)로 넘겨줍니다.

## 파일

| 파일 | 역할 |
|---|---|
| `send_event.py` | hook JSON에서 필요한 항목만 골라 bridge로 전송. bridge가 꺼져 있어도 0.7초 안에 조용히 종료(항상 성공 코드) |
| `install_hooks.py` | `~/.claude/settings.json`에 hook 등록·해제 (백업 후 합침, 다른 설정 유지) |
| `settings.example.json` | 직접 편집할 때 참고용 예시 |

## 설치 (한 번만)

```
cd web_deshboard
python hooks/install_hooks.py
```
→ `C:\Users\jang2\.claude\settings.json`에 6개 이벤트가 등록됩니다.
그다음 **Claude Code 데스크톱에서 새 세션을 시작**해야 적용됩니다. hook 설정을 확인하라는 안내가 나오면 내용을 보고 승인하세요.

해제: `python hooks/install_hooks.py --remove`

| 이벤트 | 용도 |
|---|---|
| `UserPromptSubmit` | 새 작업 시작 → READING 0% |
| `PreToolUse` (`*`) | 쓰는 도구로 단계 추정, `AskUserQuestion`이면 답변 대기 |
| `PostToolUse` (`*`) | 권한 승인·질문 답변 후 작업 중으로 복귀 |
| `Notification` | 권한 요청 → 답변 대기 |
| `Stop` | 응답 완료 → 완료 알림 |
| `SessionEnd` | 세션 종료 → 대기 |

## 연동 확인
1. bridge 실행 (`bridge/start_bridge.bat`)
2. Claude Code에서 아무 작업이나 요청
3. 확인할 곳
   - bridge 창: `PreToolUse Read → WORK READING 4%` 같은 줄이 찍힘
   - LCD: 단계명·경과 시간·진행 막대
   - `data/hook_log.jsonl`: hook이 실행될 때마다 한 줄씩 기록. **bridge가 꺼져 있어도 기록**되므로, LCD가 안 바뀌면 여기부터 확인

| 증상 | 원인·조치 |
|---|---|
| `hook_log.jsonl`이 안 생김 | hook이 실행되지 않음 → 새 세션인지, `settings.json`에 등록됐는지 확인. Claude Code에서 `/hooks` 메뉴로 등록 상태 확인 |
| 로그에 `"sent": "fail: URLError"` | bridge가 꺼져 있음 |
| 로그는 ok인데 LCD 변화 없음 | bridge 창에서 시리얼 연결 메시지 확인 (COM5, 시리얼 모니터 닫기) |

## 개인정보
프롬프트·파일 내용은 보내지 않습니다. Bash 명령은 '검토 단계' 판단을 위해 앞 120자만 bridge로 보내고, 로그·DB에는 남기지 않습니다.
연동 확인이 끝나면 `send_event.py`의 `LOG = False`로 로그를 끌 수 있습니다.
