"""bridge 실행 시작점

    python main.py                 # COM5 UNO + 웹캠 제스처 + 대시보드(http://127.0.0.1:8000)
    python main.py --port COM3     # 다른 포트
    python main.py --fake-serial   # UNO 없이 (보낼 명령을 화면에 출력)
    python main.py --no-gesture    # 웹캠 제스처 끄기 (버튼만)
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from esp32_link import Esp32Link  # noqa: E402
from lan import Beacon, lan_ipv4  # noqa: E402
from serial_link import FakeLink, SerialLink  # noqa: E402
from server import Context, Hub, create_app  # noqa: E402
from state_machine import Notifier  # noqa: E402
from storage import Store  # noqa: E402
from system_monitor import SystemMonitor  # noqa: E402


class Runner(threading.Thread):
    """상태 → UNO 명령·대시보드 반영 (0.25초마다, 또는 이벤트 즉시)"""

    def __init__(self, core: Notifier, link, hub: Hub, full_state):
        super().__init__(daemon=True, name="runner")
        self.core, self.link, self.hub, self.full_state = core, link, hub, full_state
        self.wake = threading.Event()
        self._last = None

    def kick(self) -> None:
        self.wake.set()

    def run(self) -> None:
        while True:
            self.core.tick()
            self.link.set_desired(self.core.command())
            snap = self.full_state()
            key = {k: v for k, v in snap.items() if k != "server_time"}
            if key != self._last:
                self._last = key
                self.hub.publish(snap)
            self.wake.wait(0.25)
            self.wake.clear()


def main() -> None:
    ap = argparse.ArgumentParser(description="AI 작업 알림 장치 bridge")
    ap.add_argument("--port", default=config.SERIAL_PORT)
    ap.add_argument("--http-port", type=int, default=config.HTTP_PORT)
    ap.add_argument("--fake-serial", nargs="?", const="", default=None, metavar="LOG",
                    help="UNO 없이 실행 (LOG 파일에 명령 기록 가능)")
    ap.add_argument("--no-gesture", action="store_true")
    ap.add_argument("--no-browser", action="store_true", help="실행할 때 대시보드를 열지 않음")
    ap.add_argument("--db", default=str(config.DB_PATH))
    args = ap.parse_args()

    store = Store(Path(args.db))
    core = Notifier(store, config.MIN_ALERT_SEC, config.INPUT_DELAY_SEC, config.PHASE_TAU_SEC)
    hub = Hub()
    esp32 = Esp32Link()
    system = SystemMonitor()
    holder: dict = {}

    def kick() -> None:
        if "runner" in holder:
            holder["runner"].kick()

    def on_uno_line(line: str) -> None:
        if line == "BTN" and core.on_ack("button"):
            print("        → 버튼으로 확인됨")
        kick()

    link = FakeLink(args.fake_serial or None) if args.fake_serial is not None \
        else SerialLink(args.port, config.SERIAL_BAUD, on_uno_line)

    gesture = None
    if config.GESTURE_ENABLED and not args.no_gesture:
        from presence.gesture_watch import GestureWatcher

        def on_gesture() -> None:
            if core.on_ack("gesture"):
                print("        → 제스처로 확인됨")
                kick()

        gesture = GestureWatcher(core.is_alert, on_gesture, config.GESTURE_TARGET,
                                 config.GESTURE_MIN_CONF, config.GESTURE_HOLD_SEC, config.CAMERA_INDEX)

    def full_state() -> dict:
        return {
            **core.snapshot(),
            "uno_command": core.command(),
            "device": link.status(),
            "gesture": gesture.info() if gesture else {"status": "off", "camera_on": False},
            "system": system.snapshot(),
            "esp32": esp32.status(),
            "server_time": round(time.time(), 1),
        }

    runner = Runner(core, link, hub, full_state)
    holder["runner"] = runner
    ctx = Context(core=core, store=store, hub=hub, kick=kick, full_state=full_state, system=system,
                  gesture=gesture, esp32=esp32, access_token=config.ACCESS_TOKEN,
                  lan_enabled=config.LAN_ENABLED, http_port=args.http_port,
                  lan_urls=lan_ipv4 if config.LAN_ENABLED else (lambda: []),
                  dashboard_dir=config.DASHBOARD_DIR)
    app = create_app(ctx)

    link.start()
    system.start()
    runner.start()
    if gesture:
        gesture.start()
    if config.LAN_ENABLED:
        Beacon(config.BEACON_PORT, args.http_port).start()

    url = f"http://127.0.0.1:{args.http_port}"
    print(f"bridge 실행: {url}  |  "
          f"UNO {'가짜' if args.fake_serial is not None else args.port}  |  "
          f"제스처 {'켜짐' if gesture else '꺼짐'}  |  "
          f"알림 기준: {config.MIN_ALERT_SEC:.0f}초 이상 작업, 답변 대기 {config.INPUT_DELAY_SEC:.0f}초 후")
    if config.LAN_ENABLED:
        ips = lan_ipv4()
        print(f"같은 Wi-Fi 접속 토큰: {config.ACCESS_TOKEN}   (ESP32-S3 secrets.h 의 BRIDGE_TOKEN 에 같은 값)")
        for ip in ips:
            print(f"  휴대폰 대시보드: http://{ip}:{args.http_port}/?token={config.ACCESS_TOKEN}")
        if not ips:
            print("  (같은 Wi-Fi 주소를 찾지 못했습니다. 네트워크 연결을 확인하세요)")
        print("  처음 실행 때 Windows 방화벽 창이 뜨면 '개인 네트워크'를 허용하세요.")
    print("Claude Code 이벤트를 기다리는 중… (끝내려면 Ctrl+C)")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn
    uvicorn.run(app, host=config.HTTP_HOST, port=args.http_port, log_level="warning")


if __name__ == "__main__":
    main()
