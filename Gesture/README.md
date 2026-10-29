# Gesture — 웹캠 제스처 학습기 (YOLO26 분류)

웹캠으로 제스처 사진을 클래스별로 모으고, [Ultralytics YOLO26](https://docs.ultralytics.com/ko/models/yolo26) **분류(`-cls`)** 모델을 학습합니다.
학습된 모델은 `models/gesture_cls.pt`에 저장되고, 나중에 `bridge/presence/`에서 불러 확인 제스처를 인식하는 데 씁니다.

> 탐지(`yolo26n.pt`)가 아니라 분류 모델을 쓰는 이유: 박스 라벨링 없이 "이 화면이 어떤 제스처인가"만 판단하면 되고, CPU에서도 몇 분 안에 학습됩니다.

## 실행

```
cd Gesture
pip install -r requirements.txt
python server.py
```
→ 브라우저에서 `http://localhost:8001` (bridge의 8000번과 겹치지 않음)

## 사용 순서

1. **클래스 추가** — 예: `thumbs_up`, 그리고 **`none`**(손 없음·평소 손동작·키보드 치는 모습). `none`이 없으면 아무 화면이나 제스처로 판단해 오작동합니다.
2. **촬영** — 클래스를 고르고 `Space`(1장) 또는 `B`(연속 촬영, 0.2초 간격). 클래스마다 **100장 이상**, 위치·각도·거리·조명을 바꿔 가며 찍습니다.
3. **학습** — 기본값 `yolo26n-cls`, 30 에포크, 224px. 진행 막대와 검증 정확도가 표시됩니다.
4. **실시간 테스트** — 학습된 모델로 웹캠 화면을 바로 판단해 클래스별 확률을 보여줍니다.

## 폴더 구조

| 경로 | 내용 | Git |
|---|---|---|
| `server.py` | FastAPI 서버: 촬영 저장, 학습(백그라운드), 추론 API | O |
| `web/` | 학습 페이지 (HTML·CSS·JS) | O |
| `models/gesture_cls.pt` | **최종 학습 모델** (학습할 때마다 덮어씀) | O |
| `models/gesture_cls.json` | 클래스 목록, 기반 모델, 정확도, 학습 시각 | O |
| `dataset/raw/<클래스>/` | 촬영한 원본 사진 | X (개인 데이터) |
| `dataset/split/` | 학습 직전 train/val(8:2)로 나눈 사본 | X |
| `runs/train_*/` | Ultralytics 학습 기록(그래프·가중치) | X |
| `weights/` | 자동 다운로드되는 사전학습 가중치 | X |

## 개인정보
학습용 사진은 이 PC의 `dataset/raw/`에만 저장되고 Git에 올라가지 않습니다. 학습이 끝나면 지워도 모델은 그대로 동작합니다.
(실제 알림 확인 단계에서는 프로젝트 원칙대로 영상을 저장하지 않습니다.)

## bridge에서 모델 쓰기 (예시)

```python
import cv2
from ultralytics import YOLO

model = YOLO("Gesture/models/gesture_cls.pt")
cap = cv2.VideoCapture(0)
ok, frame = cap.read()
r = model.predict(frame, imgsz=224, verbose=False)[0]
name, prob = r.names[r.probs.top1], float(r.probs.top1conf)
if name == "thumbs_up" and prob > 0.8:
    ...  # 1초 이상 연속이면 ACK
```
학습 페이지는 거울 모드로 **보여주기만** 하고 원본 방향으로 저장하므로, OpenCV 프레임을 뒤집지 않고 그대로 넣으면 됩니다.
