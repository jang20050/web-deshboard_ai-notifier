"""UNO 시리얼 연결: 원하는 명령이 바뀔 때만 전송, 끊기면 자동 재연결"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class SerialLink(threading.Thread):
    def __init__(self, port: str, baud: int, on_line: Callable[[str], None]):
        super().__init__(daemon=True, name="serial")
        self.port, self.baud, self.on_line = port, baud, on_line
        self._desired: str | None = None
        self._sent: str | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.connected = False
        self.ready = False
        self.lcd: str | None = None
        self.last_error: str | None = None
        self.last_sent: str | None = None
        self.last_sent_at: float | None = None
        self.last_rx: str | None = None
        self.last_rx_at: float | None = None
        self.last_btn_at: float | None = None
        self.connected_since: float | None = None
        self.reconnects = 0

    def set_desired(self, cmd: str) -> None:
        with self._lock:
            changed = cmd != self._desired
            self._desired = cmd
        if changed:
            self._wake.set()

    def status(self) -> dict:
        return {"port": self.port, "connected": self.connected, "ready": self.ready,
                "lcd": self.lcd, "error": self.last_error, "fake": False,
                "last_sent": self.last_sent, "last_sent_at": self.last_sent_at,
                "last_rx": self.last_rx, "last_rx_at": self.last_rx_at,
                "last_btn_at": self.last_btn_at, "connected_since": self.connected_since,
                "reconnects": self.reconnects}

    def run(self) -> None:
        import serial  # pyserial

        while True:
            try:
                ser = serial.Serial(self.port, self.baud, timeout=0)
            except serial.SerialException as e:
                if self.last_error != str(e):
                    print(f"[{_ts()}] 시리얼 {self.port} 연결 실패: {e} (2초마다 재시도)")
                self.last_error = str(e)
                self.connected = self.ready = False
                time.sleep(2)
                continue

            print(f"[{_ts()}] 시리얼 {self.port} 연결됨, UNO 부팅 대기")
            self.connected, self.ready, self.last_error = True, False, None
            self.connected_since = time.time()
            self.reconnects += 1
            self._sent = None
            opened = time.monotonic()
            buf = b""
            try:
                while True:
                    buf += ser.read(ser.in_waiting or 1)
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        line = raw.decode(errors="replace").strip()
                        if not line:
                            continue
                        self.last_rx, self.last_rx_at = line, time.time()
                        if line == "BTN":
                            self.last_btn_at = time.time()
                        if line == "READY":
                            self.ready = True
                            self._sent = None  # 재부팅 → 현재 상태 다시 전송
                        elif line.startswith("LCD,") or line == "ERR,LCD_NOT_FOUND":
                            self.lcd = line
                        if line not in ("OK", "PONG"):
                            print(f"[{_ts()}] UNO> {line}")
                        self.on_line(line)

                    # 포트를 열면 UNO가 리셋되므로 READY를 기다림 (최대 3초)
                    if not self.ready and time.monotonic() - opened > 3:
                        self.ready = True
                    if self.ready:
                        with self._lock:
                            cmd = self._desired
                        if cmd is not None and cmd != self._sent:
                            ser.write((cmd + "\n").encode("ascii", "replace"))
                            self._sent = cmd
                            self.last_sent, self.last_sent_at = cmd, time.time()
                    self._wake.wait(0.05)
                    self._wake.clear()
            except (serial.SerialException, OSError) as e:
                print(f"[{_ts()}] 시리얼 끊김: {e}")
                self.last_error = str(e)
            finally:
                self.connected = self.ready = False
                self.connected_since = None
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(1)


class FakeLink:
    """UNO 없이 시험할 때: 보낼 명령을 화면(과 파일)에 출력"""

    def __init__(self, log_path=None):
        self._sent = None
        self.connected = self.ready = True
        self.lcd = "FAKE"
        self.last_sent = None
        self.last_sent_at = None
        self.started = time.time()
        self.log = open(log_path, "a", encoding="utf-8") if log_path else None
        self.t0 = time.monotonic()

    def start(self) -> None:
        pass

    def set_desired(self, cmd: str) -> None:
        if cmd == self._sent:
            return
        self._sent = cmd
        self.last_sent, self.last_sent_at = cmd, time.time()
        print(f"[{_ts()}] (가짜 UNO) PC> {cmd}")
        if self.log:
            self.log.write(f"{(time.monotonic() - self.t0) * 1000:.0f}\t{cmd}\n")
            self.log.flush()

    def status(self) -> dict:
        return {"port": "가짜(시험)", "connected": True, "ready": True, "lcd": None, "error": None,
                "fake": True, "last_sent": self.last_sent, "last_sent_at": self.last_sent_at,
                "last_rx": None, "last_rx_at": None, "last_btn_at": None,
                "connected_since": self.started, "reconnects": 1}
