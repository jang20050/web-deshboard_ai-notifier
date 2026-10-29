"""상태 판단의 중심: hook 이벤트·확인 신호 → 장치 상태 → UNO 명령

상태: IDLE(대기) WORK(작업 중) INPUT(답변 대기) DONE(완료) ERROR(오류) SEEN(확인함)

UNO는 같은 상태 명령을 다시 받으면 소리를 처음부터 다시 냅니다(WORK 제외).
그래서 command()는 WORK가 아닌 상태에서 항상 같은 문자열을 돌려주도록 만들었습니다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Callable

from progress import INPUT_TOOLS, ProgressTracker


class St(str, Enum):
    IDLE = "IDLE"
    WORK = "WORK"
    INPUT = "INPUT"
    DONE = "DONE"
    ERROR = "ERROR"
    SEEN = "SEEN"


ALERTS = {St.INPUT, St.DONE, St.ERROR}


def mmss(sec: float) -> str:
    s = int(max(0, sec))
    return f"{s // 60:02d}:{s % 60:02d}"


def is_permission_request(evt: dict) -> bool:
    """Notification 중 '권한 요청'만 골라냄. '입력 기다리는 중(idle)' 알림은 무시."""
    ntype = (evt.get("notification_type") or "").lower()
    if ntype:
        return "permission" in ntype
    msg = (evt.get("message") or "").lower()
    return "permission" in msg or "approve" in msg


class NullStore:
    def task_start(self, *a, **k): return None
    def task_end(self, *a, **k): pass
    def event(self, *a, **k): pass
    def alert_start(self, *a, **k): return None
    def alert_ack(self, *a, **k): pass


class Notifier:
    def __init__(self, store=None, min_alert_sec: float = 20, input_delay_sec: float = 10,
                 tau: float = 45, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time):
        self.store = store or NullStore()
        self.min_alert_sec = min_alert_sec
        self.input_delay_sec = input_delay_sec
        self.tau = tau
        self.clock = clock
        self.wall = wall
        self.lock = threading.RLock()

        self.state = St.IDLE
        self.tracker: ProgressTracker | None = None
        self.task_id = None
        self.task_started: float | None = None
        self.session: str | None = None
        self.project: str | None = None
        self.pending_input_at: float | None = None
        self.input_reason: str | None = None

        self.alert_kind: St | None = None
        self.alert_id = None
        self.alert_since: float | None = None
        self.alert_text = ""
        self.alert_pct = 0
        self.idle_text = ""

        self.last_event: dict | None = None
        self.last_ack: dict | None = None
        self.timeline: deque = deque(maxlen=40)   # 현재 작업의 사건 기록 (대시보드용)
        self.task_started_wall: float | None = None
        self.last_duration: float | None = None
        self.alert_seq = 0   # 알림이 새로 날 때마다 1 증가 (ESP32-S3가 새 알림인지 구별)

    # ------------------------------------------------------------------ 입력
    def on_hook(self, evt: dict) -> None:
        with self.lock:
            now = self.clock()
            ev = evt.get("event") or ""
            tool = evt.get("tool")
            self.last_event = {"event": ev, "tool": tool, "at": self.wall()}
            if evt.get("project"):
                self.project = evt["project"]

            if ev == "UserPromptSubmit":
                self._start_task(now, evt)

            elif ev == "PreToolUse":
                if self.tracker is None:
                    self._start_task(now, evt)
                if tool in INPUT_TOOLS:
                    self._request_input(now, tool)
                else:
                    self._back_to_work(now, "answered")
                    self.tracker.on_tool(tool, evt.get("command"), now)

            elif ev == "PostToolUse":
                # 권한을 승인했거나 질문에 답해서 도구가 끝남 → 다시 작업 중
                if self.tracker is not None and (self.pending_input_at or self.state in (St.INPUT, St.SEEN)):
                    self._back_to_work(now, "answered")
                    self._log("RESUME", tool, self.tracker.phase.label, self.tracker.percent(now))

            elif ev == "Notification":
                if self.tracker is not None and is_permission_request(evt):
                    self._request_input(now, "permission")

            elif ev == "Stop":
                if self.tracker is not None:
                    self._log(ev, None, self.tracker.phase.label, self.tracker.percent(now))
                self._finish(now)

            elif ev == "SessionEnd":
                if self.state not in ALERTS:
                    self._end_task(now, "ended")
                    self.state = St.IDLE

            t = self.tracker
            if ev in ("UserPromptSubmit", "PreToolUse", "Notification", "SessionEnd"):
                self._log(ev, tool, t.phase.label if t else None, t.percent(now) if t else None)
            self.store.event(self.task_id, ev, tool,
                             t.phase.key if t else None,
                             t.percent(now) if t else None, self.wall())

    def on_ack(self, method: str) -> bool:
        """웹캠 제스처·버튼 확인. 알림 중일 때만 의미 있음."""
        with self.lock:
            if self.state not in ALERTS:
                return False
            self._close_alert(method)
            self.state = St.SEEN
            self._log("ACK", method, None, None)
            return True

    def tick(self) -> None:
        """주기적으로 호출: 미뤄 둔 '답변 대기' 알림을 시간이 되면 울림."""
        with self.lock:
            now = self.clock()
            if self.pending_input_at is not None and now >= self.pending_input_at:
                self.pending_input_at = None
                self._enter_alert(St.INPUT, now, "")

    # ------------------------------------------------------------------ 출력
    def is_alert(self) -> bool:
        with self.lock:
            return self.state in ALERTS

    def command(self) -> str:
        with self.lock:
            now = self.clock()
            if self.state == St.WORK and self.tracker:
                pct = self.tracker.percent(now)
                label = self.tracker.phase.label
                return f"S,WORK,{pct},{label:<11}{mmss(now - self.task_started)}"
            if self.state == St.INPUT:
                return f"S,INPUT,{self.alert_pct},"
            if self.state == St.DONE:
                return f"S,DONE,100,{self.alert_text}"
            if self.state == St.ERROR:
                return f"S,ERROR,{self.alert_pct},{self.alert_text}"
            if self.state == St.SEEN:
                return f"S,SEEN,{self.alert_pct},{self.alert_text}"
            return f"S,IDLE,0,{self.idle_text}"

    def snapshot(self) -> dict:
        with self.lock:
            now = self.clock()
            t = self.tracker
            return {
                "state": self.state.value,
                "phase": t.phase.key if t else None,
                "phase_label": t.phase.label if t else None,
                "percent": (t.percent(now) if t else (100 if self.state in (St.DONE, St.SEEN) else 0)),
                "elapsed_sec": int(now - self.task_started) if (t and self.task_started) else None,
                "task_id": self.task_id,
                "project": self.project,
                "alert": (self.alert_kind.value
                          if self.alert_kind and self.state in ALERTS | {St.SEEN} else None),
                "alert_elapsed_sec": int(now - self.alert_since) if (self.alert_since and self.state in ALERTS) else None,
                "input_pending": self.pending_input_at is not None,
                "lcd_text": self.alert_text if self.state in (St.DONE, St.SEEN, St.ERROR) else self.idle_text,
                "last_event": self.last_event,
                "last_ack": self.last_ack,
                "task_started_at": self.task_started_wall,
                "alert_seq": self.alert_seq,
                "last_duration_sec": round(self.last_duration) if self.last_duration is not None else None,
                "timeline": list(self.timeline),
                "input_reason": self.input_reason if (self.state == St.INPUT or self.pending_input_at) else None,
                "rules": {"min_alert_sec": self.min_alert_sec, "input_delay_sec": self.input_delay_sec},
            }

    # ------------------------------------------------------------------ 내부
    def _start_task(self, now: float, evt: dict) -> None:
        if self.tracker is not None:
            self._end_task(now, "interrupted")
        if self.state in ALERTS:
            self._close_alert("new_task")
        self.pending_input_at = None
        self.tracker = ProgressTracker(now, self.tau)
        self.task_started = now
        self.task_started_wall = self.wall()
        self.timeline.clear()
        self.session = evt.get("session")
        self.task_id = self.store.task_start(self.session, self.project, self.wall())
        self.state = St.WORK

    def _end_task(self, now: float, result: str) -> None:
        if self.tracker is None:
            return
        self.store.task_end(self.task_id, result, now - (self.task_started or now), self.wall())
        self.tracker = None

    def _request_input(self, now: float, reason: str) -> None:
        if self.state == St.INPUT or self.pending_input_at is not None:
            return
        self.input_reason = reason
        if self.input_delay_sec <= 0:
            self._enter_alert(St.INPUT, now, "")
        else:
            self.pending_input_at = now + self.input_delay_sec

    def _back_to_work(self, now: float, method: str) -> None:
        self.pending_input_at = None
        if self.state == St.INPUT:
            self._close_alert(method)
        if self.state != St.WORK:
            self.state = St.WORK

    def _enter_alert(self, kind: St, now: float, text: str) -> None:
        self.state = kind
        self.alert_kind = kind
        self.alert_seq += 1
        self.alert_since = now
        self.alert_text = text
        self.alert_pct = self.tracker.percent(now) if self.tracker else 100
        self.alert_id = self.store.alert_start(self.task_id, kind.value, self.wall())
        self._log("ALERT", kind.value, None, None)

    def _log(self, kind: str, detail, phase, pct) -> None:
        self.timeline.append({"at": round(self.wall(), 1), "kind": kind, "detail": detail,
                              "phase": phase, "pct": pct, "state": self.state.value})

    def _close_alert(self, method: str) -> None:
        if self.alert_since is None:
            return
        delay = self.clock() - self.alert_since
        self.store.alert_ack(self.alert_id, self.wall(), method, delay)
        self.last_ack = {"method": method, "delay_sec": round(delay, 1),
                         "kind": self.alert_kind.value if self.alert_kind else None, "at": self.wall()}
        self.alert_id = None
        self.alert_since = None

    def _finish(self, now: float) -> None:
        if self.tracker is None:
            return
        dur = now - (self.task_started or now)
        self.pending_input_at = None
        if self.state == St.INPUT:
            self._close_alert("answered")
        self.alert_pct = 100
        self.last_duration = dur
        self._end_task(now, "done")
        if dur >= self.min_alert_sec:
            self._enter_alert(St.DONE, now, f"TOOK {mmss(dur)}")
        else:
            self.state = St.IDLE
            self.idle_text = f"LAST OK {mmss(dur)}"
