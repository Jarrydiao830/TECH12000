"""操作员界面与控制接口：只监听本机回环地址。使能/复位只能从这台电脑上操作。"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable, Optional

import segno
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..engine import Engine
from ..hub import Hub
from ..models import Mode
from .pairing import lan_ip

STATIC = Path(__file__).parent / "static"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


class ModeBody(BaseModel):
    mode: Mode
    confirm: str = ""


class InjectBody(BaseModel):
    kind: str


class MonitoringBody(BaseModel):
    on: bool


def create_operator_app(engine: Engine, hub: Hub, get_token: Callable[[], str],
                        rotate_token: Callable[[], str], mobile_port: int,
                        sim_inject: Optional[Callable[[str], None]] = None) -> FastAPI:
    app = FastAPI(title="TECH12000 operator", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        # 纵深防御：即使被误配置成监听 0.0.0.0，也拒绝非本机来源和跨站请求
        host = request.client.host if request.client else ""
        if host not in LOOPBACK:
            return JSONResponse({"detail": "仅限本机访问"}, status_code=403)
        hdr_host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
        if hdr_host not in LOOPBACK:
            return JSONResponse({"detail": "Host 不合法"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.split("//")[-1].rsplit(":", 1)[0].strip("[]") not in LOOPBACK:
            return JSONResponse({"detail": "Origin 不合法"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        return engine.status(time.time())

    @app.get("/api/events")
    def events(limit: int = 50) -> dict:
        return {"events": engine.store.list_events(limit)}

    @app.post("/api/mode")
    def set_mode(body: ModeBody) -> dict:
        ok, why = engine.set_mode(body.mode, body.confirm)
        if not ok:
            raise HTTPException(409, why)
        return {"ok": True, "mode": engine.mode.value}

    @app.post("/api/reset")
    def reset() -> dict:
        engine.reset()
        return {"ok": True}

    @app.post("/api/monitoring")
    def monitoring(body: MonitoringBody) -> dict:
        engine.set_monitoring(body.on)
        return {"ok": True, "monitoring": engine.monitoring}

    @app.post("/api/sim/inject")
    def inject(body: InjectBody) -> dict:
        if sim_inject is None:
            raise HTTPException(409, "当前不是模拟数据源")
        try:
            sim_inject(body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    def pairing_info() -> dict:
        host, tok = lan_ip(), get_token()
        url = f"tech12000://pair?host={host}&port={mobile_port}&token={tok}"
        svg = segno.make(url, error="m").svg_inline(scale=5, border=2)
        return {"host": host, "port": mobile_port, "token": tok, "url": url, "qr_svg": svg}

    @app.get("/api/pairing")
    def pairing() -> dict:
        return pairing_info()

    @app.post("/api/pairing/rotate")
    def pairing_rotate() -> dict:
        rotate_token()
        return pairing_info()

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        host = sock.client.host if sock.client else ""
        if host not in LOOPBACK:
            await sock.close(code=4403)
            return
        await sock.accept()
        q = hub.subscribe()
        sent_n = engine.live_n
        period = 1.0 / engine.cfg.server.status_push_hz
        try:
            while True:
                deadline = time.monotonic() + period
                while True:   # 期间有事件就立刻转发
                    left = deadline - time.monotonic()
                    if left <= 0:
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=left)
                    except asyncio.TimeoutError:
                        break
                    if msg["type"] in ("event", "state"):
                        await sock.send_json(msg)
                new = min(engine.live_n - sent_n, len(engine.live_imu))
                sent_n = engine.live_n
                imu = list(engine.live_imu)[-new:] if new > 0 else []
                rf = engine.last_radar
                radar = None
                if rf is not None and engine.monitors["radar"].is_fresh(time.monotonic()):
                    radar = {"targets": [{"x": t.x, "y": t.y, "z": t.z} for t in rf.targets],
                             "n_points": None if rf.points is None else len(rf.points)}
                await sock.send_json({"type": "tick", "status": engine.status(time.time()),
                                      "imu": imu, "radar": radar})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unsubscribe(q)

    return app
