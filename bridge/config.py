"""bridge 설정값. 환경 변수로 덮어쓸 수 있습니다 (예: set NOTIFIER_PORT=COM3)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# --- 시리얼 (UNO) ---
SERIAL_PORT = os.environ.get("NOTIFIER_PORT", "COM5")
SERIAL_BAUD = 115200

# --- HTTP (hook 수신 · 대시보드) ---
# LAN_ENABLED=True : 같은 Wi-Fi의 휴대폰·ESP32-S3도 접속 가능 (접속 토큰 필요)
# LAN_ENABLED=False: 이 PC에서만 접속 (set NOTIFIER_LAN=0)
LAN_ENABLED = os.environ.get("NOTIFIER_LAN", "1") != "0"
HTTP_HOST = "0.0.0.0" if LAN_ENABLED else "127.0.0.1"
HTTP_PORT = int(_f("NOTIFIER_HTTP_PORT", 8000))
# ESP32-S3가 bridge를 자동으로 찾도록 같은 Wi-Fi에 2초마다 알리는 UDP 포트
BEACON_PORT = 47800

# --- 저장 ---
DB_PATH = ROOT / "data" / "notifier.db"
DASHBOARD_DIR = ROOT / "dashboard"

# --- 알림 규칙 ---
# 이 시간보다 짧게 끝난 작업은 부저 없이 조용히 끝냄 (짧은 대답마다 울리지 않게)
MIN_ALERT_SEC = _f("NOTIFIER_MIN_ALERT", 20)
# 권한·질문 요청 후 이 시간 안에 내가 바로 답하면 부저를 울리지 않음 (자리에 있을 때 방해 방지)
INPUT_DELAY_SEC = _f("NOTIFIER_INPUT_DELAY", 10)
# 단계 안에서 진행도가 차오르는 속도(초). 클수록 천천히 상한에 가까워짐
PHASE_TAU_SEC = _f("NOTIFIER_PHASE_TAU", 45)

# --- 웹캠 제스처 확인 (Gesture/ 에서 학습한 모델) ---
GESTURE_ENABLED = os.environ.get("NOTIFIER_GESTURE", "1") != "0"
GESTURE_TARGET = "ok"
GESTURE_MIN_CONF = 0.8
GESTURE_HOLD_SEC = 1.0
CAMERA_INDEX = int(_f("NOTIFIER_CAMERA", 0))

# --- 접속 토큰 (다른 기기에서 접속할 때 필요) ---
# 처음 실행할 때 무작위로 만들어 data/access_token.txt 에 저장합니다.
# 바꾸고 싶으면 그 파일을 지우고 다시 실행하세요 (ESP32-S3의 secrets.h 도 같이 바꿔야 함).
TOKEN_PATH = ROOT / "data" / "access_token.txt"


def _load_token() -> str:
    env = os.environ.get("NOTIFIER_TOKEN")
    if env:
        return env.strip()
    try:
        t = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(t) >= 8:
            return t
    except OSError:
        pass
    import secrets
    t = secrets.token_hex(8)  # 16자리 (0-9a-f): ESP32 설정에 옮겨 적기 쉬움
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(t + "\n", encoding="utf-8")
    return t


ACCESS_TOKEN = _load_token()
