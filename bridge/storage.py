"""SQLite 기록 (data/notifier.db). 프롬프트·파일 내용·영상은 저장하지 않습니다."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session TEXT, project TEXT,
  started REAL NOT NULL, ended REAL,
  result TEXT,            -- done / interrupted / ended
  duration_sec REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER, ts REAL NOT NULL,
  event TEXT, tool TEXT, phase TEXT, percent INTEGER
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER, kind TEXT NOT NULL,   -- INPUT / DONE / ERROR
  started REAL NOT NULL, acked REAL,
  method TEXT,                           -- gesture / button / answered / new_task
  ack_delay_sec REAL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def _exec(self, sql: str, args: tuple = ()) -> int | None:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    # Notifier가 부르는 메서드
    def task_start(self, session, project, ts):
        return self._exec("INSERT INTO tasks(session, project, started) VALUES (?,?,?)", (session, project, ts))

    def task_end(self, task_id, result, duration, ts):
        if task_id is not None:
            self._exec("UPDATE tasks SET ended=?, result=?, duration_sec=? WHERE id=?",
                       (ts, result, round(duration, 1), task_id))

    def event(self, task_id, event, tool, phase, percent, ts):
        self._exec("INSERT INTO events(task_id, ts, event, tool, phase, percent) VALUES (?,?,?,?,?,?)",
                   (task_id, ts, event, tool, phase, percent))

    def alert_start(self, task_id, kind, ts):
        return self._exec("INSERT INTO alerts(task_id, kind, started) VALUES (?,?,?)", (task_id, kind, ts))

    def alert_ack(self, alert_id, ts, method, delay):
        if alert_id is not None:
            self._exec("UPDATE alerts SET acked=?, method=?, ack_delay_sec=? WHERE id=?",
                       (ts, method, round(delay, 1), alert_id))

    # 대시보드용 조회
    def recent_tasks(self, limit: int = 20) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                """SELECT t.*, a.kind AS alert_kind, a.method AS ack_method, a.ack_delay_sec
                   FROM tasks t LEFT JOIN alerts a ON a.id = (
                     SELECT id FROM alerts WHERE task_id = t.id ORDER BY id DESC LIMIT 1)
                   ORDER BY t.id DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def today_stats(self, since_ts: float) -> dict:
        """since_ts(오늘 0시) 이후 작업·알림 요약"""
        with self.lock:
            t = self.db.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(duration_sec),0) total, COALESCE(MAX(duration_sec),0) longest "
                "FROM tasks WHERE started >= ? AND result IS NOT NULL", (since_ts,)).fetchone()
            a = self.db.execute(
                "SELECT COUNT(*) n, SUM(acked IS NOT NULL) acked FROM alerts WHERE started >= ?",
                (since_ts,)).fetchone()
            by = self.db.execute(
                "SELECT method, COUNT(*) n, AVG(ack_delay_sec) avg_delay FROM alerts "
                "WHERE started >= ? AND method IS NOT NULL GROUP BY method", (since_ts,)).fetchall()
        return {
            "tasks": t["n"], "work_sec": round(t["total"]), "longest_sec": round(t["longest"]),
            "alerts": a["n"] or 0, "acked": a["acked"] or 0,
            "by_method": {r["method"]: {"count": r["n"], "avg_delay_sec": round(r["avg_delay"] or 0, 1)}
                          for r in by},
        }

    def task_events(self, task_id: int) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT ts, event, tool, phase, percent FROM events WHERE task_id=? ORDER BY id",
                                   (task_id,)).fetchall()
        return [dict(r) for r in rows]
