from conftest import FakeClock
from state_machine import Notifier, St


def make(min_alert=20, delay=10):
    clk = FakeClock()
    return Notifier(min_alert_sec=min_alert, input_delay_sec=delay, clock=clk), clk


def hook(n, event, tool=None, **kw):
    n.on_hook({"event": event, "tool": tool, **kw})


def test_prompt_starts_work_with_progress_on_lcd():
    n, clk = make()
    hook(n, "UserPromptSubmit")
    assert n.state == St.WORK
    clk.advance(65)
    assert n.command() == "S,WORK,15,READING    01:05"


def test_work_command_changes_but_alert_commands_are_stable():
    n, clk = make()
    hook(n, "UserPromptSubmit")
    hook(n, "PreToolUse", "Edit")
    clk.advance(30)
    hook(n, "Stop")
    first = n.command()
    clk.advance(5)
    assert n.command() == first == "S,DONE,100,TOOK 00:30"  # 같은 명령 → UNO가 소리를 다시 내지 않음


def test_short_task_ends_quietly():
    n, clk = make(min_alert=20)
    hook(n, "UserPromptSubmit")
    clk.advance(5)
    hook(n, "Stop")
    assert n.state == St.IDLE
    assert n.command() == "S,IDLE,0,LAST OK 00:05"


def test_permission_waits_delay_then_alerts():
    n, clk = make(delay=10)
    hook(n, "UserPromptSubmit")
    hook(n, "PreToolUse", "Bash", command="rm -rf build")
    hook(n, "Notification", message="Claude needs your permission to use Bash")
    n.tick()
    assert n.state == St.WORK          # 아직 10초 전
    clk.advance(10)
    n.tick()
    assert n.state == St.INPUT
    assert n.command().startswith("S,INPUT,")


def test_quick_answer_cancels_pending_input():
    n, clk = make(delay=10)
    hook(n, "UserPromptSubmit")
    hook(n, "Notification", message="Claude needs your permission to use Bash")
    clk.advance(3)
    hook(n, "PostToolUse", "Bash")     # 3초 만에 승인
    clk.advance(20)
    n.tick()
    assert n.state == St.WORK


def test_idle_notification_is_ignored_after_done():
    n, clk = make()
    hook(n, "UserPromptSubmit")
    clk.advance(30)
    hook(n, "Stop")
    n.on_ack("gesture")
    clk.advance(60)
    hook(n, "Notification", message="Claude is waiting for your input", notification_type="idle_prompt")
    clk.advance(20)
    n.tick()
    assert n.state == St.SEEN


def test_ask_user_question_is_input():
    n, clk = make(delay=0)
    hook(n, "UserPromptSubmit")
    hook(n, "PreToolUse", "AskUserQuestion")
    assert n.state == St.INPUT
    hook(n, "PostToolUse", "AskUserQuestion")
    assert n.state == St.WORK
    assert n.last_ack["method"] == "answered"


def test_gesture_and_button_ack():
    n, clk = make()
    assert n.on_ack("button") is False   # 알림 아닐 때는 무시
    hook(n, "UserPromptSubmit")
    clk.advance(25)
    hook(n, "Stop")
    clk.advance(4)
    assert n.on_ack("gesture") is True
    assert n.state == St.SEEN
    assert n.last_ack == {"method": "gesture", "delay_sec": 4.0, "kind": "DONE", "at": n.last_ack["at"]}
    assert n.command() == "S,SEEN,100,TOOK 00:25"
    assert n.on_ack("button") is False   # 두 번째 확인은 무시


def test_new_prompt_after_done_restarts():
    n, clk = make()
    hook(n, "UserPromptSubmit")
    clk.advance(25)
    hook(n, "Stop")
    hook(n, "UserPromptSubmit")
    assert n.state == St.WORK
    assert n.last_ack["method"] == "new_task"


def test_pretooluse_without_prompt_starts_task():
    n, clk = make()
    hook(n, "PreToolUse", "Read")   # bridge를 작업 도중에 켠 경우
    assert n.state == St.WORK


def test_timeline_and_duration_for_dashboard():
    n, clk = make()
    hook(n, "UserPromptSubmit")
    hook(n, "PreToolUse", "Edit")
    clk.advance(30)
    hook(n, "Stop")
    n.on_ack("button")
    snap = n.snapshot()
    kinds = [e["kind"] for e in snap["timeline"]]
    assert kinds == ["UserPromptSubmit", "PreToolUse", "Stop", "ALERT", "ACK"]
    assert snap["last_duration_sec"] == 30
    assert snap["elapsed_sec"] is None
