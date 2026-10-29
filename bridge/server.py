"""FastAPI: hook 수신, 상태 조회, 대시보드 제공·실시간 WebSocket, 원격 알림 끄기

접속 규칙
  - 이 PC(127.0.0.1)에서 오는 요청: 모두 허용
  - 같은 Wi-Fi의 다른 기기(휴대폰·ESP32-S3): 접속 토큰이 맞을 때만 허용
      · 휴대폰 브라우저: 처음 한 번 http://PC주소:8000/?token=토큰 → 이후 쿠키로 기억
      · ESP32-S3: 요청 헤더 X-Notifier-Token
  - 다른 기기에서 막는 것: Claude Code hook 입력(/event), 웹캠 화면·미리보기
"""
from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
COOKIE = "notifier_token"
ACK_METHODS = {"dashboard", "phone", "esp32"}  # 원격으로 알림을 끈 경로

DENIED_PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>접속 토큰 필요</title>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.6">
<h1 style="font-size:1.4rem">접속 토큰이 필요합니다</h1>
<p>PC의 bridge 창(또는 PC에서 연 대시보드의 '같은 Wi-Fi에서 보기')에 표시된
<strong>토큰이 포함된 주소</strong>로 다시 접속해 주세요.</p>
<p style="color:#52514e">예: http://192.168.0.10:8000/?token=…</p></body></html>"""


class Hub:
    """WebSocket 접속자에게 상태를 밀어 줌 (다른 스레드에서 publish 가능)"""

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, data: dict) -> None:
        if self.loop and self.clients:
            asyncio.run_coroutine_threadsafe(self._send_all(data), self.loop)

    async def _send_all(self, data: dict) -> None:
        msg = json.dumps(data, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.clients.discard(ws)


@dataclass
class Context:
    core: Any                       # state_machine.Notifier
    store: Any                      # storage.Store
    hub: Hub
    kick: Callable[[], None]
    full_state: Callable[[], dict]  # 대시보드에 보내는 전체 상태
    system: Any = None              # system_monitor.SystemMonitor
    gesture: Any = None             # presence.gesture_watch.GestureWatcher
    esp32: Any = None               # esp32_link.Esp32Link
    access_token: str = ""
    lan_enabled: bool = False
    http_port: int = 8000
    lan_urls: Callable[[], list] = field(default=lambda: [])
    dashboard_dir: Path | None = None


def _is_local(host: str | None) -> bool:
    return (host or "") in LOCAL_HOSTS


def _token_ok(ctx: Context, token: str | None) -> bool:
    return bool(ctx.access_token) and secrets.compare_digest((token or "").encode(), ctx.access_token.encode())


def compact_state(core) -> dict:
    """ESP32-S3에 돌려주는 작은 상태 (메모리 절약)"""
    s = core.snapshot()
    return {
        "state": s["state"], "percent": s["percent"], "phase": s["phase_label"],
        "elapsed": s["elapsed_sec"], "duration": s["last_duration_sec"],
        "alert": s["alert"], "alert_elapsed": s["alert_elapsed_sec"], "alert_seq": s["alert_seq"],
        "input_reason": s["input_reason"], "input_pending": s["input_pending"],
        "project": s["project"],
        "last_ack": (s["last_ack"] or {}).get("method"),
    }


def create_app(ctx: Context) -> FastAPI:
    app = FastAPI(title="AI Agent Notifier bridge", docs_url=None, redoc_url=None, openapi_url=None)
    core, store = ctx.core, ctx.store

    @app.on_event("startup")
    async def _startup():
        ctx.hub.loop = asyncio.get_running_loop()

    # ---------------------------------------------------------------- 접속 검사
    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.client.host if request.client else None
        if _is_local(host):
            return await call_next(request)
        path = request.url.path
        if path == "/event" or path.startswith("/api/camera"):
            return JSONResponse({"ok": False, "error": "이 기능은 PC에서만 쓸 수 있습니다"}, status_code=403)
        q = request.query_params.get("token")
        token = request.headers.get("x-notifier-token") or q or request.cookies.get(COOKIE)
        if not _token_ok(ctx, token):
            if path.startswith("/api/"):
                return JSONResponse({"ok": False, "error": "접속 토큰이 맞지 않습니다"}, status_code=401)
            return HTMLResponse(DENIED_PAGE, status_code=401)
        response = await call_next(request)
        if q:  # 주소에 붙여 온 토큰은 쿠키로 기억 (다음부터 주소에 없어도 됨)
            response.set_cookie(COOKIE, q, max_age=60 * 60 * 24 * 30, httponly=True, samesite="strict")
        return response

    # ---------------------------------------------------------------- Claude Code hook (PC 전용)
    @app.post("/event")
    async def event(req: Request):
        try:
            evt = await req.json()
        except Exception:
            return {"ok": False, "error": "json"}
        core.on_hook(evt)
        ctx.kick()
        s = core.snapshot()
        tool = f" {evt.get('tool')}" if evt.get("tool") else ""
        pct = f" {s['percent']}%" if s["state"] == "WORK" else ""
        phase = f" {s['phase_label']}" if s["state"] == "WORK" and s["phase_label"] else ""
        wait = " (답변 대기 예약)" if s["input_pending"] else ""
        print(f"[{datetime.now():%H:%M:%S}] {evt.get('event')}{tool} → {s['state']}{phase}{pct}{wait}")
        return {"ok": True, "state": s["state"]}

    # ---------------------------------------------------------------- 조회
    @app.get("/api/state")
    def state():
        return ctx.full_state()

    @app.get("/api/access")
    def access(req: Request):
        """대시보드가 'PC에서 보는지, 다른 기기에서 보는지' 알기 위한 정보"""
        local = _is_local(req.client.host if req.client else None)
        info = {"local": local, "lan_enabled": ctx.lan_enabled}
        if local:  # 토큰과 접속 주소는 PC 화면에만 보여 줌
            info["urls"] = [f"http://{ip}:{ctx.http_port}/?token={ctx.access_token}" for ip in ctx.lan_urls()]
            info["token"] = ctx.access_token
        else:
            # 이미 토큰으로 들어온 기기에만 도달하는 응답. 브라우저가 WebSocket 연결에 쿠키를
            # 보내지 않는 경우가 있어, 실시간 연결 주소에 붙일 값으로 돌려줌
            info["ws_token"] = ctx.access_token
        return info

    @app.get("/api/tasks")
    def tasks(limit: int = 20):
        return store.recent_tasks(min(max(limit, 1), 200))

    @app.get("/api/tasks/{task_id}/events")
    def task_events(task_id: int):
        return store.task_events(task_id)

    @app.get("/api/stats")
    def stats():
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return store.today_stats(midnight)

    @app.get("/api/system/history")
    def system_history():
        return ctx.system.history_list() if ctx.system else []

    # ---------------------------------------------------------------- 원격 알림 끄기
    @app.post("/api/ack")
    async def ack(req: Request):
        try:
            body = await req.json()
        except Exception:
            body = {}
        method = body.get("method") if isinstance(body, dict) else None
        method = method if method in ACK_METHODS else "dashboard"
        acked = core.on_ack(method)
        ctx.kick()
        if acked:
            who = req.client.host if req.client else "?"
            print(f"[{datetime.now():%H:%M:%S}] 원격으로 확인됨 ({method}, {who})")
        return {"ok": True, "acked": acked, "state": core.snapshot()["state"]}

    # ---------------------------------------------------------------- 웹캠 (PC 전용, 메모리의 최신 1장)
    @app.get("/api/camera.jpg")
    def camera():
        jpg = ctx.gesture.frame() if ctx.gesture else None
        if not jpg:
            return Response(status_code=204)
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/camera/preview")
    async def camera_preview(req: Request):
        if not ctx.gesture:
            return {"ok": False, "error": "제스처 기능이 꺼져 있습니다"}
        try:
            body = await req.json()
        except Exception:
            body = {}
        ok = ctx.gesture.start_preview(float(body.get("seconds", 30)))
        ctx.kick()
        return {"ok": ok, "error": None if ok else "카메라를 아직 사용할 수 없습니다"}

    @app.delete("/api/camera/preview")
    def camera_preview_stop():
        if ctx.gesture:
            ctx.gesture.stop_preview()
            ctx.kick()
        return {"ok": True}

    # ---------------------------------------------------------------- ESP32-S3
    @app.post("/api/esp32/heartbeat")
    async def esp32_heartbeat(req: Request):
        """ESP32-S3가 1초마다 자기 상태를 보내고, 응답으로 AI 작업 상태를 받아 감"""
        try:
            data = await req.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "json"}, status_code=400)
        if isinstance(data, dict):
            data.setdefault("remote_ip", req.client.host if req.client else None)
            ctx.esp32.heartbeat(data)
        ctx.kick()
        return {"ok": True, **compact_state(core)}

    @app.get("/api/esp32")
    def esp32():
        return ctx.esp32.status()

    # ---------------------------------------------------------------- 실시간
    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        host = sock.client.host if sock.client else None
        if not _is_local(host) and not _token_ok(ctx, sock.query_params.get("token") or sock.cookies.get(COOKIE)):
            await sock.close(code=4401)
            return
        await sock.accept()
        ctx.hub.clients.add(sock)
        try:
            await sock.send_text(json.dumps(ctx.full_state(), ensure_ascii=False))
            while True:
                await sock.receive_text()  # 받은 내용은 무시
        except WebSocketDisconnect:
            pass
        finally:
            ctx.hub.clients.discard(sock)

    if ctx.dashboard_dir and (ctx.dashboard_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(ctx.dashboard_dir), html=True), name="dashboard")
    else:
        @app.get("/", response_class=HTMLResponse)
        def placeholder():
            return ("<!doctype html><html lang='ko'><meta charset='utf-8'><title>Notifier bridge</title>"
                    "<body style='font-family:sans-serif;padding:2rem'><h1>bridge 실행 중</h1>"
                    "<p>dashboard/index.html 이 없습니다. 지금 상태: <a href='/api/state'>/api/state</a></p>")

    return app
