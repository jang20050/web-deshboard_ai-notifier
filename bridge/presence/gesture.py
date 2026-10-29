"""웹캠 손 제스처 확인 감지 (Gesture/ 에서 학습한 YOLO26 분류 모델 사용)

정해진 제스처(기본 "ok")가 일정 확률 이상으로 hold_sec 동안 끊김 없이 보이면 확인으로 판단한다.
영상은 저장하지 않고, 프레임마다 판단 결과만 돌려준다.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "Gesture" / "models" / "gesture_cls.pt"


@dataclass
class GestureResult:
    name: str  # 이번 프레임에서 가장 확률이 높은 클래스
    prob: float
    held: float  # 목표 제스처가 연속으로 보인 시간(초)
    confirmed: bool  # held 가 hold_sec 이상이 된 순간 True


class GestureDetector:
    def __init__(self, model_path: Path = DEFAULT_MODEL, target: str = "ok",
                 min_conf: float = 0.8, hold_sec: float = 1.0, imgsz: int = 224):
        from ultralytics import YOLO

        self.model = YOLO(str(model_path))
        if target not in self.model.names.values():
            raise ValueError(f"모델에 '{target}' 클래스가 없습니다: {list(self.model.names.values())}")
        self.target = target
        self.min_conf = min_conf
        self.hold_sec = hold_sec
        self.imgsz = imgsz
        self._since: float | None = None  # 목표 제스처가 처음 보인 시각

    def reset(self) -> None:
        self._since = None

    def update(self, frame: np.ndarray) -> GestureResult:
        """BGR 프레임 한 장을 판단한다. OpenCV 원본 방향 그대로 넣는다(뒤집지 않음)."""
        r = self.model.predict(frame, imgsz=self.imgsz, verbose=False)[0]
        name, prob = r.names[r.probs.top1], float(r.probs.top1conf)

        now = time.monotonic()
        if name == self.target and prob >= self.min_conf:
            if self._since is None:
                self._since = now
            held = now - self._since
        else:
            self._since = None
            held = 0.0
        return GestureResult(name, prob, held, held >= self.hold_sec)
