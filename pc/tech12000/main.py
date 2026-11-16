"""启动入口。

  tech12000 run            运行（默认模拟数据源；真实硬件在 config/local.yaml 里切换）
  tech12000 replay <dir>   离线回放一段录制
  tech12000 ports          列出本机串口
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import time

from .config import Config, load_config

log = logging.getLogger("tech12000")


def build(cfg: Config):
    from .actuators import make_led, make_servo
    from .engine import Engine
    from .recorder import Recorder
    from .sources.sim import SimRadar, SimScenario, SimWristband
    from .store import Store

    store = Store(f"{cfg.data_dir}/tech12000.sqlite3")
    rec = Recorder(cfg.data_dir, cfg.model_dump(mode="json"), cfg.version_hash())
    servo = make_servo(cfg.actuators.servo)
    servo.open()

    # LED 驱动可能依赖接收板串口，所以先建引擎（LED 占位），再建数据源，最后替换 LED
    from .actuators.base import LedDriver
    engine = Engine(cfg, store, servo, LedDriver(), rec)
    scenario = SimScenario()
    sources, sim_inject, receiver_send = [], None, None

    w = cfg.sources.wristband
    if w.driver == "sim":
        sources.append(SimWristband(engine, scenario))
    elif w.driver == "serial":
        from .sources.wristband_serial import SerialWristband
        sw = SerialWristband(engine, w)
        sources.append(sw)
        receiver_send = sw.send_command
        engine.status_providers["receiver"] = sw.board_status
    elif w.driver != "none":
        raise ValueError(f"未知手环驱动 {w.driver}")

    r = cfg.sources.radar
    if r.driver == "sim":
        sources.append(SimRadar(engine, scenario))
    elif r.driver == "rs6240":
        from .sources.radar_rs6240 import Rs6240Radar
        sources.append(Rs6240Radar(engine, r))
    elif r.driver != "none":
        raise ValueError(f"未知雷达驱动 {r.driver}")

    if "sim" in (w.driver, r.driver):
        sim_inject = lambda kind: scenario.inject(kind, time.monotonic())
        engine.on_reset_hooks.append(scenario.reset)

    engine.led = make_led(cfg.actuators.led, receiver_send)
    return engine, store, rec, sources, sim_inject


async def run_async(cfg: Config) -> None:
    import uvicorn

    from .apns import ApnsSender
    from .hub import Hub
    from .server import pairing
    from .server.mobile import create_mobile_app
    from .server.operator import create_operator_app

    engine, store, rec, sources, sim_inject = build(cfg)
    hub = Hub()
    apns = ApnsSender(cfg.apns, store)
    token = {"v": pairing.load_or_create_token(cfg.data_dir)}
    loop = asyncio.get_running_loop()
    bg: set = set()

    def listener(kind: str, payload: dict) -> None:
        hub.publish({"type": kind, kind: payload})
        if kind == "event" and cfg.apns.enabled:
            ev = engine.last_event
            if ev is not None and ev.event_id == payload["event_id"]:
                t = loop.create_task(apns.notify(ev))   # 推送失败/变慢不影响本地
                bg.add(t)
                t.add_done_callback(bg.discard)

    engine.listeners.append(listener)

    def rotate() -> str:
        token["v"] = pairing.rotate_token(cfg.data_dir)
        return token["v"]

    s = cfg.server
    op_app = create_operator_app(engine, hub, lambda: token["v"], rotate, s.mobile_port, sim_inject)
    mb_app = create_mobile_app(engine, hub, lambda: token["v"])

    class Server(uvicorn.Server):
        # 两个服务共用一个事件循环，信号由本函数统一处理
        def install_signal_handlers(self) -> None:
            pass

        @contextlib.contextmanager
        def capture_signals(self):
            yield

    servers = [
        Server(uvicorn.Config(op_app, host=s.operator_host, port=s.operator_port, log_level="warning")),
        Server(uvicorn.Config(mb_app, host=s.mobile_host, port=s.mobile_port, log_level="warning")),
    ]

    def stop(*_):
        for sv in servers:
            sv.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop)

    async def ticker() -> None:
        while True:
            engine.tick(time.monotonic(), time.time())
            await asyncio.sleep(0.02)

    tasks = [asyncio.create_task(src.run()) for src in sources] + [asyncio.create_task(ticker())]
    log.info("操作员界面: http://%s:%d", s.operator_host, s.operator_port)
    log.info("手机接口:   http://%s:%d  （配对信息见操作员界面）", pairing.lan_ip(), s.mobile_port)
    log.info("日志目录:   %s", rec.dir)
    try:
        await asyncio.gather(*(sv.serve() for sv in servers))
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        engine.servo.close()
        rec.close()
        store.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="tech12000")
    ap.add_argument("--config-dir", default="config")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run")
    rp = sub.add_parser("replay")
    rp.add_argument("session_dir")
    rp.add_argument("--mode", default="monitor", choices=["monitor", "demo"])
    sub.add_parser("ports")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "ports":
        from serial.tools import list_ports
        for p in list_ports.comports():
            print(f"{p.device}\t{p.description}\tVID:PID={p.vid}:{p.pid}")
        return
    cfg = load_config(args.config_dir)
    if args.cmd == "replay":
        from .models import Mode
        from .replay import replay
        print(json.dumps(replay(args.session_dir, cfg, Mode(args.mode)), ensure_ascii=False, indent=2))
        return
    asyncio.run(run_async(cfg))


if __name__ == "__main__":
    main()
