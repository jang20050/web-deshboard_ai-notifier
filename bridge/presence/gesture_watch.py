"""알림이 울리는 동안(또는 대시보드 미리보기 중)에만 웹캠을 켜서 확인 제스처를 찾는 스레드

- 평소에는 카메라를 열지 않음 (카메라 표시등 꺼짐, CPU 절약, 평소 손동작 오작동 방지)
- 대시보드용 화면은 메모리에 최신 1장만 두고, 파일로 저장하지 않음
- 미리보기(카메라 위치 맞추기)에서는 제스처를 인식해도 알림을 끄지 않음
- 모델이나 카메라에 문제가 있어도 bridge는 계속 동작 (빵판 버튼으로 확인 가능)
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Callable

PREVIEW_MAX_SEC = 60
FRAME_INTERVAL = 0.15   # 대시보드용 JPEG 갱신 간격(초)
FRAME_WIDTH = 480


class GestureWatcher(threading.Thread):
    def __init__(self, is_alert: Callable[[], bool], on_confirm: Callable[[], None],
                 target: str, min_conf: float, hold_sec: float, camera_index: int):
        super().__init__(daemon=True, name="gesture")
        self.is_alert, self.on_confirm = is_alert, on_confirm
        self.target, self.min_conf, self.hold_sec = target, min_conf, hold_sec
        self.camera_index = camera_index
        self.status = "loading"        # loading / idle / watching / preview / disabled / camera_error
        self.detail: str | None = None
        self.last: dict | None = None  # 마지막 판단 {name, prob, held}
        self.last_confirm_at: float | None = None
        self.preview_until = 0.0
        self._jpeg: bytes | None = None
        self._jpeg_at = 0.0
        self._lock = threading.Lock()

    # ---- 대시보드에서 사용
    def info(self) -> dict:
        now = time.time()
        return {"status": self.status, "detail": self.detail, "last": self.last,
                "target": self.target, "hold_sec": self.hold_sec, "min_conf": self.min_conf,
                "camera_on": self.status in ("watching", "preview"),
                "preview_left_sec": max(0, round(self.preview_until - now)) if self.status == "preview" else 0,
                "last_confirm_at": self.last_confirm_at}

    def start_preview(self, seconds: float = 30) -> bool:
        if self.status in ("disabled", "loading"):
            return False
        self.preview_until = time.time() + min(max(seconds, 5), PREVIEW_MAX_SEC)
        return True

    def stop_preview(self) -> None:
        self.preview_until = 0.0

    def frame(self) -> bytes | None:
        with self._lock:
            if self._jpeg and time.time() - self._jpeg_at < 2:
                return self._jpeg
        return None

    # ---- 스레드
    def run(self) -> None:
        try:
            import cv2
            from presence.gesture import GestureDetector
            det = GestureDetector(target=self.target, min_conf=self.min_conf, hold_sec=self.hold_sec)
        except Exception as e:  # 모델 파일 없음, ultralytics 미설치 등
            self.status, self.detail = "disabled", str(e)
            print(f"[{datetime.now():%H:%M:%S}] 제스처 확인 끔: {e}")
            return

        print(f"[{datetime.now():%H:%M:%S}] 제스처 모델 준비됨 (대상: '{self.target}', {self.hold_sec}초 유지)")
        self.status = "idle"
        backend = cv2.CAP_DSHOW if os.name == "nt" else 0
        cap = None
        while True:
            alert = self.is_alert()
            preview = time.time() < self.preview_until
            if not alert and not preview:
                if cap is not None:
                    cap.release()
                    cap = None
                    det.reset()
                with self._lock:
                    self._jpeg = None
                self.last = None
                self.status = "idle"
                time.sleep(0.2)
                continue

            if cap is None:
                cap = cv2.VideoCapture(self.camera_index, backend)
                if not cap.isOpened():
                    self.status, self.detail = "camera_error", f"카메라 {self.camera_index} 열기 실패"
                    cap = None
                    time.sleep(2)
                    continue
                det.reset()
                self.detail = None
            self.status = "watching" if alert else "preview"

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            res = det.update(frame)
            self.last = {"name": res.name, "prob": round(res.prob, 2), "held": round(res.held, 2),
                         "confirmed": bool(res.confirmed)}

            now = time.time()
            if now - self._jpeg_at >= FRAME_INTERVAL:
                view = cv2.flip(frame, 1)  # 대시보드에는 거울 모드로
                h, w = view.shape[:2]
                if w > FRAME_WIDTH:
                    view = cv2.resize(view, (FRAME_WIDTH, int(h * FRAME_WIDTH / w)))
                ok_enc, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok_enc:
                    with self._lock:
                        self._jpeg, self._jpeg_at = buf.tobytes(), now

            if res.confirmed:
                det.reset()
                if alert:
                    self.last_confirm_at = now
                    self.on_confirm()
