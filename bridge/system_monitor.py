"""컴퓨터 상태: CPU 사용량·온도, 메모리, 배터리 (2초마다, 최근 10분 보관)

CPU 온도는 Windows가 기본으로 알려주지 않습니다. 아래 순서로 시도하고, 읽을 수 없으면 값을 만들지 않고
'측정 불가'와 이유를 돌려줍니다.
  1. psutil (Linux·일부 환경)
  2. LibreHardwareMonitor 원격 웹 서버  http://127.0.0.1:8085/data.json   ← 권장
  3. LibreHardwareMonitor WMI (프로그램만 실행 중일 때, PowerShell로 조회)
  4. ACPI 열 영역 (관리자 권한 필요, 메인보드 온도라 CPU와 다를 수 있음)
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from collections import deque

LHM_URL = os.environ.get("NOTIFIER_LHM_URL", "http://127.0.0.1:8085/data.json")
HISTORY_SEC = 600
INTERVAL = 2.0
TEMP_INTERVAL = 5.0

# 판단 기준 (대시보드 상태 문구와 같은 값)
CPU_WARN, CPU_HIGH = 75, 90          # %
TEMP_WARN, TEMP_HIGH = 80, 90        # °C
MEM_WARN, MEM_HIGH = 80, 90          # %
BATT_WARN, BATT_LOW = 30, 15         # %


def level(value, warn, high, reverse=False):
    if value is None:
        return "unknown"
    if reverse:
        return "critical" if value <= high else "warning" if value <= warn else "good"
    return "critical" if value >= high else "warning" if value >= warn else "good"


# ---------------------------------------------------------------- CPU 온도
def _parse_c(text) -> float | None:
    try:
        return float(str(text).replace(",", ".").split("°")[0].strip())
    except (ValueError, AttributeError):
        return None


def _lhm_web() -> tuple[float | None, str | None]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.loads(opener.open(LHM_URL, timeout=1.0).read().decode("utf-8", "replace"))
    found: dict[str, float] = {}

    def walk(node, in_cpu=False):
        text = str(node.get("Text", ""))
        img = str(node.get("ImageURL", "")).lower()
        cpu_here = in_cpu or "cpu" in img or any(k in text for k in ("Intel", "AMD Ryzen", "CPU"))
        val = node.get("Value", "")
        if cpu_here and isinstance(val, str) and "°C" in val:
            v = _parse_c(val)
            if v is not None:
                found[text] = v
        for ch in node.get("Children", []) or []:
            walk(ch, cpu_here)

    walk(data)
    for key in ("CPU Package", "Core (Tctl/Tdie)", "Core (Tctl)", "Core Average", "Core Max", "CPU Core"):
        if key in found:
            return found[key], f"LibreHardwareMonitor · {key}"
    if found:
        k, v = max(found.items(), key=lambda kv: kv[1])
        return v, f"LibreHardwareMonitor · {k}"
    return None, None


def _powershell(cmd: str) -> str:
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                         text=True, timeout=4, creationflags=flags)
    return out.stdout.strip()


def _lhm_wmi() -> tuple[float | None, str | None]:
    out = _powershell(
        "Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor -ErrorAction Stop | "
        "Where-Object { $_.SensorType -eq 'Temperature' -and $_.Identifier -match 'cpu' } | "
        "Select-Object Name,Value | ConvertTo-Json -Compress")
    if not out:
        return None, None
    rows = json.loads(out)
    rows = rows if isinstance(rows, list) else [rows]
    by = {r["Name"]: float(r["Value"]) for r in rows if r.get("Value") is not None}
    for key in ("CPU Package", "Core (Tctl/Tdie)", "Core Average", "Core Max"):
        if key in by:
            return by[key], f"LibreHardwareMonitor WMI · {key}"
    if by:
        k, v = max(by.items(), key=lambda kv: kv[1])
        return v, f"LibreHardwareMonitor WMI · {k}"
    return None, None


def _acpi() -> tuple[float | None, str | None]:
    out = _powershell(
        "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop)"
        ".CurrentTemperature | ConvertTo-Json -Compress")
    if not out:
        return None, None
    vals = json.loads(out)
    vals = vals if isinstance(vals, list) else [vals]
    temps = [v / 10 - 273.15 for v in vals if isinstance(v, (int, float)) and v > 0]
    if temps:
        return round(max(temps), 1), "ACPI 열 영역 (메인보드 기준, CPU와 다를 수 있음)"
    return None, None


def _psutil_temp(psutil) -> tuple[float | None, str | None]:
    fn = getattr(psutil, "sensors_temperatures", None)
    if not fn:
        return None, None
    temps = fn() or {}
    for key in ("coretemp", "k10temp", "cpu_thermal", "zenpower"):
        if temps.get(key):
            return max(t.current for t in temps[key]), f"psutil · {key}"
    return None, None


class SystemMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="system")
        self.history: deque = deque(maxlen=int(HISTORY_SEC / INTERVAL))
        self.current: dict = {"available": False}
        self._temp = {"value": None, "source": None, "note": "확인 중"}
        self._temp_at = 0.0
        self._temp_provider = None   # 성공한 방법을 기억해 다음부터 그것만 사용
        self._cpu_high_since = None
        self.lock = threading.Lock()

    def _read_temp(self, psutil) -> None:
        providers = [("psutil", lambda: _psutil_temp(psutil)), ("lhm_web", _lhm_web)]
        if os.name == "nt":
            providers += [("lhm_wmi", _lhm_wmi), ("acpi", _acpi)]
        if self._temp_provider:
            providers.sort(key=lambda p: p[0] != self._temp_provider)
        for name, fn in providers:
            try:
                v, src = fn()
            except Exception:
                continue
            if v is not None and -20 < v < 130:
                self._temp_provider = name
                self._temp = {"value": round(v, 1), "source": src, "note": None}
                return
        self._temp_provider = None
        self._temp = {"value": None, "source": None,
                      "note": "이 PC에서 CPU 온도를 읽을 수 없습니다. LibreHardwareMonitor를 실행하고 "
                              "'Options → Remote Web Server → Run'을 켜 주세요."}

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            self.current = {"available": False, "note": "psutil 미설치 (pip install psutil)"}
            return
        psutil.cpu_percent(None)
        while True:
            now = time.time()
            if now - self._temp_at >= TEMP_INTERVAL:
                self._temp_at = now
                self._read_temp(psutil)
                if self._temp["value"] is None:
                    self._temp_at = now + 55  # 못 읽으면 1분 뒤 다시 시도 (PowerShell 부담 줄이기)

            cpu = psutil.cpu_percent(None)
            mem = psutil.virtual_memory()
            batt = None
            try:
                b = psutil.sensors_battery()
                if b is not None:
                    batt = {"percent": round(b.percent), "plugged": b.power_plugged,
                            "secs_left": b.secsleft if isinstance(b.secsleft, int) and b.secsleft > 0 else None}
            except Exception:
                batt = None

            # 과부하: CPU 사용량이 높은 상태가 30초 이상 이어질 때
            if cpu >= CPU_HIGH:
                self._cpu_high_since = self._cpu_high_since or now
            else:
                self._cpu_high_since = None
            sustained = self._cpu_high_since is not None and now - self._cpu_high_since >= 30

            temp = self._temp["value"]
            levels = {
                "cpu": "critical" if sustained else level(cpu, CPU_WARN, CPU_HIGH),
                "temp": level(temp, TEMP_WARN, TEMP_HIGH),
                "mem": level(mem.percent, MEM_WARN, MEM_HIGH),
                "battery": level(batt["percent"], BATT_WARN, BATT_LOW, reverse=True)
                if batt and not batt["plugged"] else ("good" if batt else "unknown"),
            }
            order = ["unknown", "good", "warning", "critical"]
            overall = max((levels[k] for k in ("cpu", "temp", "mem")), key=order.index)

            sample = {"ts": round(now, 1), "cpu": round(cpu, 1), "temp": temp, "mem": round(mem.percent, 1)}
            with self.lock:
                self.history.append(sample)
                self.current = {
                    "available": True,
                    "ts": sample["ts"],
                    "cpu_percent": sample["cpu"],
                    "cpu_count": psutil.cpu_count(),
                    "cpu_high_sec": int(now - self._cpu_high_since) if self._cpu_high_since else 0,
                    "temp": dict(self._temp),
                    "mem_percent": sample["mem"],
                    "mem_used_gb": round(mem.used / 1024 ** 3, 1),
                    "mem_total_gb": round(mem.total / 1024 ** 3, 1),
                    "battery": batt,
                    "levels": levels,
                    "overall": overall,
                    "thresholds": {"cpu": [CPU_WARN, CPU_HIGH], "temp": [TEMP_WARN, TEMP_HIGH],
                                   "mem": [MEM_WARN, MEM_HIGH], "battery": [BATT_WARN, BATT_LOW]},
                }
            time.sleep(INTERVAL)

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.current)

    def history_list(self) -> list[dict]:
        with self.lock:
            return list(self.history)
