"""ESP32-S3 상태 수신 (준비 단계)

ESP32-S3가 Wi-Fi로 bridge에 주기적으로 보내는 '하트비트'를 받아 대시보드에 보여 줍니다.
아직 ESP32-S3가 없으므로 지금은 '미연결'로 표시되고, 없는 값은 만들지 않습니다.

ESP32-S3가 보낼 내용 (POST /api/esp32/heartbeat, 헤더 X-Notifier-Token)
    {"chip_temp_c": 41.5,   # ESP32-S3 칩 내부 온도 (주변 온도 아님, 오차 큼)
     "rssi_dbm": -58,       # Wi-Fi 신호 세기
     "ip": "192.168.0.23", "uptime_s": 3600, "fw": "0.1.0", "free_heap": 210000,
     "simulated": false}    # 시험용 가짜 데이터면 true (대시보드에 표시됨)

※ 지금 bridge는 이 PC(127.0.0.1)에서만 접속을 받습니다. 실제 ESP32-S3를 연결할 때
  접속 범위(HTTP_HOST)와 토큰을 함께 바꾸는 작업을 다음 단계에서 합니다.
"""
from __future__ import annotations

import threading
import time
from collections import deque

ONLINE_SEC = 15  # 이 시간 안에 하트비트가 왔으면 '연결됨'
FIELDS = ("chip_temp_c", "rssi_dbm", "ip", "uptime_s", "fw", "free_heap", "simulated",
          "phone_url", "ntfy", "push_ok", "push_age_s", "found_by", "remote_ip")


def rssi_quality(rssi) -> str | None:
    if not isinstance(rssi, (int, float)):
        return None
    return "좋음" if rssi >= -60 else "보통" if rssi >= -70 else "약함" if rssi >= -80 else "매우 약함"


class Esp32Link:
    def __init__(self):
        self.lock = threading.Lock()
        self.last: dict | None = None
        self.last_at: float | None = None
        self.first_at: float | None = None
        self.count = 0
        self.gaps: deque = deque(maxlen=60)  # 하트비트 간격(초) → 통신 안정성

    def heartbeat(self, data: dict) -> None:
        now = time.time()
        clean = {k: data.get(k) for k in FIELDS if k in data}
        with self.lock:
            if self.last_at:
                self.gaps.append(round(now - self.last_at, 1))
            self.first_at = self.first_at or now
            self.last, self.last_at = clean, now
            self.count += 1

    def status(self) -> dict:
        with self.lock:
            now = time.time()
            if self.last_at is None:
                return {"state": "never", "label": "연결된 적 없음", "data": None,
                        "last_seen_sec": None, "count": 0}
            age = now - self.last_at
            online = age <= ONLINE_SEC
            gaps = list(self.gaps)
            return {
                "state": "online" if online else "offline",
                "label": "연결됨" if online else "끊김",
                "data": self.last,
                "rssi_quality": rssi_quality((self.last or {}).get("rssi_dbm")),
                "last_seen_sec": int(age),
                "count": self.count,
                "avg_interval_sec": round(sum(gaps) / len(gaps), 1) if gaps else None,
            }
