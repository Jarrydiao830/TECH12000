"""模拟数据源：无硬件时驱动整套流程，也供测试使用。

波形是人为构造的，只用于验证软件链路和状态机逻辑，
【不代表真实跌倒或日常动作的信号形态】，不能用来评估检测性能。
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Optional

from ..models import ImuSample, RadarFrame, RadarTarget

G = 9.81
STAND_Z = 1.0
SCENARIOS = ("idle", "fall", "wave", "squat")


class SimScenario:
    """当前剧本。fall 结束后目标保持低位，直到 reset()。"""

    def __init__(self) -> None:
        self.kind = "idle"
        self.t0 = 0.0
        self._rng = random.Random(12000)

    def inject(self, kind: str, now: float) -> None:
        if kind not in SCENARIOS:
            raise ValueError(f"未知剧本 {kind}")
        self.kind, self.t0 = kind, now

    def reset(self) -> None:
        self.kind = "idle"

    def wrist(self, now: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        n = lambda s: self._rng.gauss(0, s)
        accel = [n(0.15), n(0.15), G + n(0.15)]
        gyro = [n(2), n(2), n(2)]
        dt = now - self.t0
        if self.kind == "fall":
            if 0.0 <= dt < 0.35:          # 失重段
                accel[2] = 1.5 + n(0.3)
                gyro[0] = 320 + n(20)
            elif 0.35 <= dt < 0.45:       # 冲击段
                accel[2] = 38 + n(2)
                gyro[1] = 250 + n(20)
        elif self.kind == "wave" and 0.0 <= dt < 2.0:   # 只有手腕剧烈运动
            accel[0] = 32 * math.sin(2 * math.pi * 3 * dt)
            gyro[2] = 450 * math.cos(2 * math.pi * 3 * dt)
        elif self.kind == "squat" and 0.0 <= dt < 3.0:
            accel[2] = G + 1.5 * math.sin(2 * math.pi * dt / 3.0)
            gyro[0] = 40 * math.sin(2 * math.pi * dt / 3.0)
        return tuple(accel), tuple(gyro)  # type: ignore[return-value]

    def height(self, now: float) -> float:
        dt = now - self.t0
        z = STAND_Z
        if self.kind == "fall":
            z = STAND_Z - 0.8 * min(max(dt / 0.6, 0.0), 1.0)
        elif self.kind == "squat" and 0.0 <= dt < 3.0:   # 慢蹲慢起
            z = STAND_Z - 0.55 * math.sin(math.pi * dt / 3.0)
        return z + self._rng.gauss(0, 0.01)


class SimWristband:
    name = "wristband"

    def __init__(self, sink, scenario: SimScenario, rate_hz: float = 100.0):
        self.sink, self.scn, self.dt = sink, scenario, 1.0 / rate_hz
        self.session_id = random.getrandbits(32)
        self.seq = 0
        self._t_boot = time.monotonic()

    def make(self, now: float, wall: Optional[float] = None) -> ImuSample:
        a, g = self.scn.wrist(now)
        self.seq += 1
        return ImuSample(
            device_id="sim-wrist", session_id=self.session_id, seq=self.seq, accel=a, gyro=g,
            t_pc=now, t_wall=time.time() if wall is None else wall,
            t_mcu_us=int((now - self._t_boot) * 1e6), simulated=True)

    async def run(self) -> None:
        mon = self.sink.monitors[self.name]
        mon.connected, mon.detail = True, "模拟数据"
        nxt = time.monotonic()
        while True:
            self.sink.on_imu(self.make(time.monotonic()))
            nxt += self.dt
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))

    def send_command(self, cmd: dict) -> bool:
        return True


class SimRadar:
    name = "radar"

    def __init__(self, sink, scenario: SimScenario, rate_hz: float = 20.0):
        self.sink, self.scn, self.dt = sink, scenario, 1.0 / rate_hz
        self.seq = 0

    def make(self, now: float, wall: Optional[float] = None) -> RadarFrame:
        self.seq += 1
        tg = RadarTarget(track_id=1, x=0.0, y=1.5, z=self.scn.height(now))
        return RadarFrame(seq=self.seq, t_pc=now, t_wall=time.time() if wall is None else wall,
                          targets=[tg], simulated=True)

    async def run(self) -> None:
        mon = self.sink.monitors[self.name]
        mon.connected, mon.detail = True, "模拟数据"
        nxt = time.monotonic()
        while True:
            self.sink.on_radar(self.make(time.monotonic()))
            nxt += self.dt
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))
