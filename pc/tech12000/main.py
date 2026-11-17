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
        raise ValueError(f"Unknown wristband driver {w.driver}")

    r = cfg.sources.radar
    if r.driver == "sim":
        sources.append(SimRadar(engine, scenario))
    elif r.driver == "rs6240":
        from .sources.radar_rs6240 import Rs6240Radar
        rr = Rs6240Radar(engine, r)
        sources.append(rr)
        engine.status_providers["radar_hif"] = rr.status
    elif r.driver != "none":
        raise ValueError(f"Unknown radar driver {r.driver}")

    if "sim" in (w.driver, r.driver):
        def sim_inject(kind: str) -> None:
            scenario.inject(kind, time.monotonic())
            engine.sim_label = scenario.label
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
    log.info("Operator UI: http://%s:%d", s.operator_host, s.operator_port)
    log.info("Phone API:   http://%s:%d  (pairing info is on the operator UI)", pairing.lan_ip(), s.mobile_port)
    log.info("Log folder:  %s", rec.dir)
    try:
        await asyncio.gather(*(sv.serve() for sv in servers))
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        engine.servo.close()
        rec.close()
        store.close()


def imu_probe(args) -> None:
    import serial
    from .sources.yb_imu import YbImuParser, build_set_rate

    p, n, last = YbImuParser(), 0, None
    with serial.Serial(args.port, 115200, timeout=0.1) as ser:
        if args.rate:
            ser.write(build_set_rate(args.rate))
        t0 = time.monotonic()
        while time.monotonic() - t0 < args.seconds:
            for a, g in p.feed(ser.read(256)):
                n, last = n + 1, (a, g)
                if n % 25 == 1:
                    print("accel m/s² " + " ".join(f"{x:+7.2f}" for x in a)
                          + "   gyro °/s " + " ".join(f"{x:+8.1f}" for x in g))
        dt = time.monotonic() - t0
    print(f"\n{n} raw frames, about {n / dt:.1f} Hz; stats {p.stats}")
    if last:
        import math
        print(f"Last frame |a| = {math.sqrt(sum(x * x for x in last[0])):.2f} m/s² (should be close to 9.8 when still)")


def radar_probe(args) -> None:
    from .sources.radar_rs6240 import Rs6240Decoder

    dec = Rs6240Decoder()
    raw = bytearray()
    shown = 0

    def handle(data: bytes) -> None:
        nonlocal shown
        raw.extend(data)
        for pc in dec.feed(data):
            if shown < 20:
                zs = [p[2] for p in pc.points]
                rng = f"z {min(zs):+.2f}..{max(zs):+.2f} m" if zs else ""
                print(f"frame {pc.frame_idx:>8}  {pc.kind:<8} {'cart' if pc.cartesian else 'polar'}"
                      f"  points={len(pc.points):<4} {rng}")
                shown += 1

    if args.file:
        handle(open(args.file, "rb").read())
    else:
        import serial
        with serial.Serial(args.port, args.baud, timeout=0.1) as ser:
            end = time.monotonic() + args.seconds
            print(f"Listening on {args.port} @ {args.baud} for {args.seconds:.0f} s (sending nothing)...")
            while time.monotonic() < end:
                d = ser.read(4096)
                if d:
                    handle(d)
    if args.save:
        open(args.save, "wb").write(raw)
    print(f"\nReceived {len(raw)} bytes")
    print(json.dumps(dec.stats(), ensure_ascii=False, indent=2))
    if raw and not dec.parser.stats["frames"]:
        print("No HIF frames parsed. First 64 bytes:", raw[:64].hex(" "))
        print("Possible causes: wrong baud rate / this is the debug log port / firmware needs the host to poll first / HIF is on SPI")


def main() -> None:
    ap = argparse.ArgumentParser(prog="tech12000")
    ap.add_argument("--config-dir", default="config")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run")
    rp = sub.add_parser("replay")
    rp.add_argument("session_dir")
    rp.add_argument("--mode", default="monitor", choices=["monitor", "demo"])
    sub.add_parser("ports")
    pp = sub.add_parser("radar-probe", help="Read an RS6240 serial port or capture file and count HIF frames and point clouds (read-only, sends no commands)")
    src = pp.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--file", help="Raw bytes saved earlier with --save")
    pp.add_argument("--baud", type=int, default=1_000_000)
    pp.add_argument("--seconds", type=float, default=10.0)
    pp.add_argument("--save", help="Save the received raw bytes to this file")
    ip = sub.add_parser("imu-probe", help="Read raw accel/gyro from a Yahboom IMU over direct USB (for troubleshooting)")
    ip.add_argument("--port", required=True)
    ip.add_argument("--seconds", type=float, default=5.0)
    ip.add_argument("--rate", type=int, help="First set the output rate, 10-100 Hz (no reply)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "ports":
        from serial.tools import list_ports
        for p in list_ports.comports():
            print(f"{p.device}\t{p.description}\tVID:PID={p.vid}:{p.pid}")
        return
    if args.cmd == "imu-probe":
        imu_probe(args)
        return
    if args.cmd == "radar-probe":
        radar_probe(args)
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
