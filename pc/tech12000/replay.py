"""离线回放：把一段录制的 stream.jsonl 以原始时间戳重新喂给引擎（不等待、不碰硬件）。

用途：同一批数据上比较不同阈值/规则。执行器强制为模拟，事件库在内存中。
"""
from __future__ import annotations

import json
from pathlib import Path

from .actuators.base import SimLed, SimServo
from .config import Config
from .engine import Engine
from .models import ImuSample, Mode, RadarFrame, RadarTarget
from .recorder import NullRecorder
from .store import Store


def replay(session_dir: str | Path, cfg: Config, mode: Mode = Mode.MONITOR) -> dict:
    path = Path(session_dir) / "stream.jsonl"
    eng = Engine(cfg, Store(":memory:"), SimServo(), SimLed(), NullRecorder(), inline_actuation=True)
    eng.mode = mode
    transitions: list[dict] = []
    events: list[dict] = []

    def listener(kind: str, payload: dict) -> None:
        if kind == "state":
            transitions.append(payload)
        elif kind == "event":
            events.append(payload)

    eng.listeners.append(listener)
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            k = o.pop("k", None)
            if k == "imu":
                o["accel"], o["gyro"] = tuple(o["accel"]), tuple(o["gyro"])
                o["t_est"] = None
                eng.on_imu(ImuSample(**o))
                n += 1
            elif k == "radar":
                o["targets"] = [RadarTarget(**t) for t in o["targets"]]
                o["t_est"] = None
                eng.on_radar(RadarFrame(**o))
                n += 1
            elif k == "reset":
                eng.reset()
    return {"records": n, "transitions": transitions, "events": events,
            "config_version": cfg.version_hash()}
