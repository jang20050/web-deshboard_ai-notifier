"""제스처 학습기 서버 (FastAPI + Ultralytics YOLO26 분류).

웹캠 사진을 클래스별로 모으고, YOLO26 분류 모델을 학습해 models/ 에 저장한다.
실행: python server.py  →  http://localhost:8001
"""

import json
import os
import random
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "dataset" / "raw"  # 촬영 원본: raw/<클래스>/*.jpg
SPLIT_DIR = BASE_DIR / "dataset" / "split"  # 학습 직전 train/val 로 나눈 사본
RUNS_DIR = BASE_DIR / "runs"  # Ultralytics 학습 결과(그래프·가중치)
MODELS_DIR = BASE_DIR / "models"  # 최종 모델: gesture_cls.pt + gesture_cls.json
WEIGHTS_DIR = BASE_DIR / "weights"  # 사전학습 가중치(yolo26n-cls.pt 등) 다운로드 위치
WEB_DIR = BASE_DIR / "web"

MODEL_PATH = MODELS_DIR / "gesture_cls.pt"
MODEL_INFO_PATH = MODELS_DIR / "gesture_cls.json"

PORT = 8001  # bridge 가 8000 을 쓰므로 겹치지 않게
VAL_RATIO = 0.2
CLASS_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ALLOWED_SIZES = {"n", "s", "m"}

for d in (RAW_DIR, MODELS_DIR, WEIGHTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Gesture Trainer")

train_lock = threading.Lock()
train_state = {
    "running": False,
    "epoch": 0,
    "epochs": 0,
    "message": "대기 중",
    "metrics": {},
    "error": None,
    "finished_at": None,
}

model_lock = threading.Lock()
_model = None
_model_mtime = None


# ---------- 공통 ----------

def check_class_name(name: str) -> str:
    if not CLASS_NAME_RE.match(name):
        raise HTTPException(400, "클래스 이름은 영문·숫자·_·- 만 1~32자로 써 주세요.")
    return name


def list_classes() -> list[dict]:
    classes = []
    for d in sorted(p for p in RAW_DIR.iterdir() if p.is_dir()):
        classes.append({"name": d.name, "count": len(list(d.glob("*.jpg")))})
    return classes


def decode_jpeg(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "이미지를 읽을 수 없습니다.")
    return img


def load_model():
    """학습된 모델을 불러온다. 파일이 새로 바뀌었으면 다시 불러온다."""
    global _model, _model_mtime
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    with model_lock:
        if _model is None or mtime != _model_mtime:
            from ultralytics import YOLO

            _model = YOLO(str(MODEL_PATH))
            _model_mtime = mtime
        return _model


def read_model_info() -> dict | None:
    if not MODEL_INFO_PATH.exists():
        return None
    return json.loads(MODEL_INFO_PATH.read_text(encoding="utf-8"))


# ---------- 클래스·촬영 ----------

class NewClass(BaseModel):
    name: str


@app.get("/api/classes")
def get_classes():
    return {"classes": list_classes()}


@app.post("/api/classes")
def add_class(body: NewClass):
    name = check_class_name(body.name.strip())
    (RAW_DIR / name).mkdir(exist_ok=True)
    return {"classes": list_classes()}


@app.delete("/api/classes/{name}")
def delete_class(name: str):
    check_class_name(name)
    target = RAW_DIR / name
    if not target.exists():
        raise HTTPException(404, "없는 클래스입니다.")
    shutil.rmtree(target)
    return {"classes": list_classes()}


@app.delete("/api/classes/{name}/last")
def delete_last_image(name: str):
    """방금 찍은 사진이 잘못됐을 때 마지막 1장만 지운다."""
    check_class_name(name)
    images = sorted((RAW_DIR / name).glob("*.jpg"))
    if images:
        images[-1].unlink()
    return {"classes": list_classes()}


@app.post("/api/capture/{name}")
async def capture(name: str, request: Request):
    """본문으로 받은 JPEG 한 장을 raw/<클래스>/ 에 저장한다."""
    check_class_name(name)
    folder = RAW_DIR / name
    if not folder.exists():
        raise HTTPException(404, "먼저 클래스를 추가해 주세요.")
    data = await request.body()
    decode_jpeg(data)  # 깨진 파일이 학습에 섞이지 않도록 확인만 한다
    filename = f"{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
    (folder / filename).write_bytes(data)
    return {"count": len(list(folder.glob("*.jpg")))}


# ---------- 학습 ----------

class TrainRequest(BaseModel):
    epochs: int = Field(30, ge=1, le=300)
    imgsz: int = Field(224, ge=64, le=640)
    size: str = "n"


def build_split(classes: list[str]) -> None:
    """raw/ 를 train/val 로 나눠 split/ 에 복사한다 (Ultralytics 분류 폴더 구조)."""
    if SPLIT_DIR.exists():
        shutil.rmtree(SPLIT_DIR)
    rng = random.Random(0)
    for name in classes:
        images = sorted((RAW_DIR / name).glob("*.jpg"))
        rng.shuffle(images)
        n_val = max(1, int(len(images) * VAL_RATIO))
        for subset, files in (("val", images[:n_val]), ("train", images[n_val:])):
            out = SPLIT_DIR / subset / name
            out.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.copy2(f, out / f.name)


def run_training(req: TrainRequest, classes: list[str]) -> None:
    try:
        from ultralytics import YOLO

        train_state["message"] = "데이터 나누는 중"
        build_split(classes)

        train_state["message"] = f"yolo26{req.size}-cls 사전학습 가중치 준비 중"
        model = YOLO(str(WEIGHTS_DIR / f"yolo26{req.size}-cls.pt"))

        def on_epoch_end(trainer):
            # 마지막 최종 검증 때 한 번 더 불리므로 에포크 수를 넘지 않게 자른다
            epoch = min(trainer.epoch + 1, trainer.epochs)
            train_state["epoch"] = epoch
            train_state["metrics"] = {
                k.split("/")[-1]: round(float(v), 4) for k, v in (trainer.metrics or {}).items()
            }
            train_state["message"] = f"학습 중 ({epoch}/{trainer.epochs} 에포크)"

        model.add_callback("on_fit_epoch_end", on_epoch_end)

        train_state["message"] = "학습 시작"
        run_name = datetime.now().strftime("train_%Y%m%d_%H%M%S")
        model.train(
            data=str(SPLIT_DIR),
            epochs=req.epochs,
            imgsz=req.imgsz,
            batch=16,
            workers=0,  # Windows 에서 스레드 안 학습 시 멀티프로세스 로더 문제를 피함
            project=str(RUNS_DIR),
            name=run_name,
            exist_ok=True,
            plots=True,
            verbose=False,
        )

        best = Path(model.trainer.best)
        if not best.exists():
            raise RuntimeError("best.pt 가 만들어지지 않았습니다.")
        shutil.copy2(best, MODEL_PATH)
        info = {
            "classes": classes,
            "base_model": f"yolo26{req.size}-cls.pt",
            "epochs": req.epochs,
            "imgsz": req.imgsz,
            "metrics": train_state["metrics"],
            "images": {c["name"]: c["count"] for c in list_classes() if c["name"] in classes},
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "run_dir": str(best.parent.parent.relative_to(BASE_DIR)),
        }
        MODEL_INFO_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        train_state["message"] = "학습 완료 — models/gesture_cls.pt 에 저장했습니다"
    except Exception as e:  # 학습 실패를 화면에 보여주기 위해 모두 잡는다
        train_state["error"] = str(e)
        train_state["message"] = "학습 실패"
    finally:
        train_state["running"] = False
        train_state["finished_at"] = time.time()


@app.post("/api/train")
def start_training(req: TrainRequest):
    if req.size not in ALLOWED_SIZES:
        raise HTTPException(400, "모델 크기는 n, s, m 중 하나입니다.")
    classes = [c for c in list_classes() if c["count"] > 0]
    if len(classes) < 2:
        raise HTTPException(400, "사진이 있는 클래스가 2개 이상 필요합니다.")
    too_few = [c["name"] for c in classes if c["count"] < 10]
    if too_few:
        raise HTTPException(400, f"클래스마다 최소 10장이 필요합니다: {', '.join(too_few)}")

    with train_lock:
        if train_state["running"]:
            raise HTTPException(409, "이미 학습 중입니다.")
        train_state.update(
            running=True, epoch=0, epochs=req.epochs, message="준비 중",
            metrics={}, error=None, finished_at=None,
        )
    threading.Thread(target=run_training, args=(req, [c["name"] for c in classes]), daemon=True).start()
    return train_state


@app.get("/api/train/status")
def training_status():
    return {**train_state, "model": read_model_info()}


# ---------- 테스트(추론) ----------

@app.post("/api/predict")
async def predict(request: Request):
    model = load_model()
    if model is None:
        raise HTTPException(404, "아직 학습된 모델이 없습니다.")
    img = decode_jpeg(await request.body())
    info = read_model_info() or {}
    with model_lock:
        result = model.predict(img, imgsz=info.get("imgsz", 224), verbose=False)[0]
    probs = result.probs.data.tolist()
    ranked = sorted(
        ({"name": result.names[i], "prob": round(p, 4)} for i, p in enumerate(probs)),
        key=lambda r: r["prob"],
        reverse=True,
    )
    return {"top": ranked[0], "all": ranked}


# ---------- 정적 파일 ----------

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")


if __name__ == "__main__":
    os.chdir(BASE_DIR)  # Ultralytics 가 만드는 부수 파일도 Gesture/ 안에 두기
    uvicorn.run(app, host="127.0.0.1", port=PORT)
