"""제스처로 부저 멈추기 시험

사용법 (bridge 폴더에서):
    python tools/gesture_ack_test.py            # 기본 COM5, 완료 알림
    python tools/gesture_ack_test.py COM5 INPUT # 답변 대기 알림으로 시험

UNO에 알림(완료: 초록 + 도-미-솔)을 보내 부저를 울리고, 웹캠 창을 연다.
"ok" 제스처를 1초 유지하면 ACK 를 보내 부저를 멈춘다. 빵판 버튼(BTN)으로 멈춰도 기록한다.
웹캠 창에서 q 또는 Esc 로 종료. 영상은 저장하지 않는다.
"""
import sys
import time
from pathlib import Path

import cv2
import serial  # pyserial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presence.gesture import GestureDetector  # noqa: E402

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
ALERT = sys.argv[2].upper() if len(sys.argv) > 2 else "DONE"
BAUD = 115200
CAMERA = 0
TIMEOUT_SEC = 60
WINDOW = "Gesture ACK test (q: quit)"


def draw(frame, res, hold_sec, banner):
    view = cv2.flip(frame, 1)  # 화면에만 거울 모드
    ok = res.name == "ok"
    color = (60, 200, 60) if ok else (200, 200, 200)
    cv2.rectangle(view, (0, 0), (view.shape[1], 70), (0, 0, 0), -1)
    cv2.putText(view, f"{res.name} {res.prob * 100:.0f}%", (12, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
    # 1초 유지 진행 막대
    w = int((view.shape[1] - 24) * min(res.held / hold_sec, 1.0))
    cv2.rectangle(view, (12, 48), (view.shape[1] - 12, 60), (80, 80, 80), 1)
    if w:
        cv2.rectangle(view, (12, 48), (12 + w, 60), (60, 200, 60), -1)
    if banner:
        cv2.putText(view, banner, (12, view.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 220, 255), 3)
    return view


def main() -> None:
    print("모델 불러오는 중…")
    detector = GestureDetector()

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0)
    except serial.SerialException as e:
        print(f"{PORT} 열기 실패: {e}\n- 시리얼 모니터나 다른 시험 스크립트를 닫아 주세요")
        sys.exit(1)

    cap = cv2.VideoCapture(CAMERA, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("웹캠을 열 수 없습니다.")
        sys.exit(1)

    time.sleep(2.0)  # 포트를 열면 UNO가 리셋됨
    ser.reset_input_buffer()
    ser.write(f"S,{ALERT},100,SHOW OK SIGN\n".encode())
    t0 = time.monotonic()
    print(f"UNO > {ALERT} 알림 시작. 카메라에 'ok' 제스처를 1초 유지하세요.")

    rx = b""
    acked_at = None
    method = None
    try:
        while True:
            ok_read, frame = cap.read()
            if not ok_read:
                continue
            res = detector.update(frame)

            # UNO 에서 온 줄 읽기 (버튼)
            rx += ser.read(ser.in_waiting or 0)
            while b"\n" in rx:
                line, rx = rx.split(b"\n", 1)
                if line.strip() == b"BTN" and acked_at is None:
                    acked_at, method = time.monotonic(), "버튼"

            if res.confirmed and acked_at is None:
                ser.write(b"ACK\n")
                acked_at, method = time.monotonic(), "제스처"

            banner = f"ACK by {'GESTURE' if method == '제스처' else 'BUTTON'}" if acked_at else ""
            cv2.imshow(WINDOW, draw(frame, res, detector.hold_sec, banner))
            key = cv2.waitKey(1) & 0xFF

            if acked_at and time.monotonic() - acked_at > 2.0:
                break
            if key in (ord("q"), 27) or time.monotonic() - t0 > TIMEOUT_SEC:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if acked_at:
            print(f"확인됨: {method}, 알림 후 {acked_at - t0:.1f}초")
        else:
            print("확인되지 않고 종료 → 부저 정지")
            ser.write(b"ACK\n")
        time.sleep(0.2)
        ser.write(b"S,IDLE,0,\n")
        time.sleep(0.2)
        ser.close()


if __name__ == "__main__":
    main()
