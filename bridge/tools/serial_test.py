"""UNO 알림 장치 시리얼 시험 스크립트

사용법 (bridge 폴더에서):
    pip install pyserial
    python tools/serial_test.py            # 기본 COM5
    python tools/serial_test.py COM3       # 다른 포트

시험 순서: 연결 → PING → 작업 중(10·55·100%) → 답변 대기 → 완료 → 오류 → 대기
알림(답변 대기·완료) 단계에서는 빵판 버튼을 눌러 보세요. BTN이 찍히면 성공입니다.
아두이노 IDE의 시리얼 모니터가 열려 있으면 포트를 쓸 수 없으니 먼저 닫으세요.
"""
import sys
import threading
import time

import serial  # pyserial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
BAUD = 115200

STEPS = [
    ("PING", 1, "연결 확인 → PONG"),
    ("S,WORK,10,READING FILES", 3, "파랑 숨쉬기, LCD 막대 10%"),
    ("S,WORK,55,BUILDING", 3, "청록 숨쉬기, 막대 55%"),
    ("S,WORK,100,REVIEWING", 3, "초록 숨쉬기, 막대 100%"),
    ("S,INPUT,90,", 8, "주황 깜빡임 + 띵-동 반복(최대 10회), LCD 경과 시간  ← 버튼을 눌러 보세요"),
    ("S,DONE,100,TOOK 12M", 9, "초록 + 도미솔 반복(최대 10회)  ← 버튼을 눌러 보세요"),
    ("S,ERROR,0,HOOK FAIL", 3, "빨강 2번 깜빡인 뒤 켜짐 + 낮은 음 1회"),
    ("S,IDLE,0,TEST DONE", 1, "흰색 약하게, READY"),
]


def reader(ser: serial.Serial, stop: threading.Event) -> None:
    while not stop.is_set():
        line = ser.readline().decode(errors="replace").strip()
        if line:
            mark = "  ★ 버튼 눌림!" if line == "BTN" else ""
            print(f"    UNO> {line}{mark}")


def main() -> None:
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.2)
    except serial.SerialException as e:
        print(f"{PORT} 열기 실패: {e}\n- 포트 번호 확인(장치 관리자), 시리얼 모니터 닫기")
        sys.exit(1)

    print(f"{PORT} 연결됨. UNO 재부팅 대기 2초…")
    stop = threading.Event()
    threading.Thread(target=reader, args=(ser, stop), daemon=True).start()
    time.sleep(2.0)  # 포트를 열면 UNO가 리셋됨

    try:
        for cmd, wait, expect in STEPS:
            print(f"\nPC > {cmd}\n    기대: {expect}")
            ser.write((cmd + "\n").encode())
            time.sleep(wait)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        ser.close()
        print("\n끝. LCD가 비어 있으면 위 로그의 LCD 주소 줄과 README의 '문제 해결'을 확인하세요.")


if __name__ == "__main__":
    main()
