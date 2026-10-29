"""같은 Wi-Fi 연결: 이 PC의 주소 찾기, ESP32-S3가 bridge를 자동으로 찾도록 알리기(비컨)

비컨: 2초마다 같은 네트워크에 UDP 방송으로
    {"svc": "ai-notifier", "port": 8000, "name": "DESK-05"}
를 보냅니다. ESP32-S3는 이 패킷을 받은 주소를 bridge 주소로 씁니다.
(토큰은 보내지 않습니다. ESP32-S3는 자기 설정 파일의 토큰을 씁니다.)
"""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time


def lan_ipv4() -> list[str]:
    """이 PC의 사설망(공유기 안) IPv4 주소들. 기본 경로 주소를 맨 앞에."""
    found: list[str] = []
    try:
        # 실제로 패킷을 보내지 않고, 밖으로 나갈 때 쓰는 주소만 알아냄
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.0.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    out = []
    for ip in found:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private and not a.is_loopback and not ip.startswith("169.254."):
            out.append(ip)
    return out


class Beacon(threading.Thread):
    def __init__(self, port: int, http_port: int, interval: float = 2.0):
        super().__init__(daemon=True, name="beacon")
        self.port, self.http_port, self.interval = port, http_port, interval
        self.sent = 0
        self.error: str | None = None

    def run(self) -> None:
        msg = json.dumps({"svc": "ai-notifier", "port": self.http_port, "name": socket.gethostname()}).encode()
        while True:
            targets = {"255.255.255.255"}
            for ip in lan_ipv4():  # 어댑터가 여러 개인 PC 대비: 각 /24 대역 방송 주소에도
                targets.add(ip.rsplit(".", 1)[0] + ".255")
            for t in targets:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        s.sendto(msg, (t, self.port))
                    self.sent += 1
                    self.error = None
                except OSError as e:
                    self.error = str(e)
            time.sleep(self.interval)
