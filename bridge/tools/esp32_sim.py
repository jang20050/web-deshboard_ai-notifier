"""ESP32-S3 없이 대시보드의 ESP32 패널을 시험: 가짜 하트비트를 2초마다 보냄

    python bridge/tools/esp32_sim.py            # 60초 동안
    python bridge/tools/esp32_sim.py 300        # 300초 동안

보내는 값에는 "simulated": true 가 붙어 대시보드에 '시뮬레이션 데이터'로 표시됩니다.
끝나면 15초 뒤 대시보드가 '끊김'으로 바뀌는지도 확인할 수 있습니다.
"""
import json
import math
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8000/api/esp32/heartbeat"
from pathlib import Path

# bridge가 처음 실행될 때 만든 접속 토큰 (이 PC에서 보낼 때는 없어도 되지만 실제 ESP32와 같게 보냄)
_tok = Path(__file__).resolve().parents[2] / "data" / "access_token.txt"
TOKEN = _tok.read_text(encoding="utf-8").strip() if _tok.exists() else ""

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 60
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
t0 = time.monotonic()
n = 0
while time.monotonic() - t0 < duration:
    t = time.monotonic() - t0
    body = {
        "chip_temp_c": round(42 + 3 * math.sin(t / 20), 1),
        "rssi_dbm": int(-60 + 6 * math.sin(t / 7)),
        "ip": "192.168.0.50",
        "uptime_s": int(t),
        "fw": "sim-0.1",
        "free_heap": 210_000,
        "simulated": True,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Notifier-Token": TOKEN})
    try:
        opener.open(req, timeout=1).read()
        n += 1
        print(f"\r보냄 {n}회  온도 {body['chip_temp_c']}°C  RSSI {body['rssi_dbm']} dBm", end="")
    except Exception as e:
        print(f"\r전송 실패: {e} (bridge가 켜져 있나요?)", end="")
    time.sleep(2)
print("\n끝")
