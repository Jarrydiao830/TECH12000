"""手机接口（局域网，只读，需配对令牌）。

这里【没有也不允许添加】任何改变模式、使能、复位或触发执行的接口：
App 只监控，不参与融合判断，不提供远程释放或远程使能。
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..engine import Engine
from ..hub import Hub
from .pairing import token_ok

MOBILE_KINDS = ("state", "event", "mode", "reset", "monitoring")


def mobile_status(engine: Engine) -> dict:
    """给手机的精简状态，不含原始曲线。"""
    s = engine.status(time.time())
    dev = s["devices"]
    return {
        "server_time": s["server_time"],
        "state": s["state"], "state_reason": s["state_reason"], "mode": s["mode"],
        "monitoring": s["monitoring"],
        "devices": {
            k: {"connected": v.get("connected"), "fresh": v.get("fresh"),
                "last_rx_wall": v.get("last_rx_wall"), "detail": v.get("detail", ""),
                "simulated": v.get("simulated")}
            for k, v in dev.items()
        },
        "deploy_status": s["deploy_status"], "deploy_outcome": s["deploy_outcome"],
        "last_event": s["last_event"], "simulated_input": s["simulated_input"],
    }


class ApnsToken(BaseModel):
    token: str = Field(min_length=32, max_length=200, pattern=r"^[0-9a-fA-F]+$")


def create_mobile_app(engine: Engine, hub: Hub, get_token) -> FastAPI:
    app = FastAPI(title="TECH12000 mobile API", docs_url=None, redoc_url=None, openapi_url=None)

    def auth(authorization: str | None = Header(default=None)) -> None:
        if not token_ok(get_token(), authorization):
            raise HTTPException(401, "Not paired or token invalid")

    r = APIRouter(prefix="/api/v1", dependencies=[Depends(auth)])

    @r.get("/status")
    def status() -> dict:
        return mobile_status(engine)

    @r.get("/events")
    def events(limit: int = 20) -> dict:
        return {"events": engine.store.list_events(max(1, min(limit, 100)))}

    @r.get("/events/{event_id}")
    def event(event_id: str) -> dict:
        ev = engine.store.get_event(event_id)
        if ev is None:
            raise HTTPException(404, "No such event")
        return ev

    @r.post("/apns/token")
    def apns_token(body: ApnsToken) -> dict:
        engine.store.add_apns_token(body.token.lower())
        return {"ok": True}

    app.include_router(r)

    @app.websocket("/api/v1/ws")
    async def ws(sock: WebSocket) -> None:
        if not token_ok(get_token(), sock.headers.get("authorization")):
            await sock.close(code=4401)
            return
        await sock.accept()
        q = hub.subscribe()
        try:
            await sock.send_json({"type": "status", "status": mobile_status(engine)})
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    # 设备在线状态的定时上报（与人体心跳无关）
                    await sock.send_json({"type": "status", "status": mobile_status(engine)})
                    continue
                if msg["type"] == "event":
                    await sock.send_json(msg)
                if msg["type"] in MOBILE_KINDS:
                    await sock.send_json({"type": "status", "status": mobile_status(engine)})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unsubscribe(q)

    return app
