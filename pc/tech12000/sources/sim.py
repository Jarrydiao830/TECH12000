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
FALLS = ("fall_forward", "fall_backward", "fall_side", "slip", "faint")
SCENARIOS = ("idle", "fall", *FALLS, "wave", "squat")
ALIASES = {"fall": "fall_forward"}
LABELS = {"fall_forward": "Forward fall", "fall_backward": "Backward fall", "fall_side": "Sideways fall",
          "slip": "Slip and fall", "faint": "Faint (collapse)", "wave": "Wave (wrist only)",
          "squat": "Slow squat", "idle": "Idle"}

# Wrist IMU per fall type: (t_from, t_to, accel xyz, gyro xyz). None keeps the resting value + noise.
# Made-up shapes for testing the software only; real falls have to be recorded.
WRIST = {
    "fall_forward": [(0.0, 0.35, (None, None, 1.5), (320, None, None)),          # free fall
                     (0.35, 0.45, (None, None, 38), (None, 250, None))],         # impact
    "fall_backward": [(0.0, 0.40, (None, None, 2.0), (None, -300, None)),
                      (0.40, 0.50, (-6, None, 42), (None, -260, None))],
    "fall_side": [(0.0, 0.30, (None, None, 1.8), (350, None, None)),
                  (0.30, 0.40, (None, 12, 45), (280, None, None))],
    "slip": [(0.0, 0.12, (15, None, None), (None, -150, None)),                  # feet shoot out
             (0.12, 0.40, (None, None, 1.0), (None, -420, None)),
             (0.40, 0.48, (None, None, 50), (None, -200, None))],                # hard landing on the hip
    "faint": [(0.0, 0.90, (None, None, 7.5), (40, None, None)),                  # legs give way slowly
              (0.90, 1.35, (None, None, 3.5), (None, None, 230)),                # tips over
              (1.35, 1.45, (None, 8, 29), (120, None, None))],                   # softer impact
}
# Gravity direction on the wrist once lying (sensor axes): body orientation has changed.
LYING_G = {"fall_forward": (G, 0, 0), "fall_backward": (-G, 0, 0), "fall_side": (0, G, 0),
           "slip": (-G, 0, 0), "faint": (0, G, 0)}
WRIST_END = {k: v[-1][1] for k, v in WRIST.items()}


def _ramp(t: float, a: float, b: float, power: float = 1.0) -> float:
    return min(max((t - a) / (b - a), 0.0), 1.0) ** power


class SimScenario:
    """当前剧本。跌倒结束后人保持躺在地上，直到 reset()。"""

    def __init__(self) -> None:
        self.kind = "idle"
        self.t0 = 0.0
        self._rng = random.Random(12000)

    def inject(self, kind: str, now: float) -> None:
        if kind not in SCENARIOS:
            raise ValueError(f"Unknown scenario {kind}")
        self.kind, self.t0 = ALIASES.get(kind, kind), now

    def reset(self) -> None:
        self.kind = "idle"

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, self.kind)

    def wrist(self, now: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        n = lambda s: self._rng.gauss(0, s)
        accel = [n(0.15), n(0.15), G + n(0.15)]
        gyro = [n(2), n(2), n(2)]
        dt = now - self.t0
        if self.kind in WRIST:
            if dt >= WRIST_END[self.kind]:
                accel = [g + n(0.15) for g in LYING_G[self.kind]]
            for a, b, acc, gyr in WRIST[self.kind]:
                if a <= dt < b:
                    for i in range(3):
                        if acc[i] is not None:
                            accel[i] = acc[i] + n(abs(acc[i]) * 0.06 + 0.2)
                        if gyr[i] is not None:
                            gyro[i] = gyr[i] + n(20)
        elif self.kind == "wave" and 0.0 <= dt < 2.0:   # 只有手腕剧烈运动
            accel[0] = 32 * math.sin(2 * math.pi * 3 * dt)
            gyro[2] = 450 * math.cos(2 * math.pi * 3 * dt)
        elif self.kind == "squat" and 0.0 <= dt < 3.0:
            accel[2] = G + 1.5 * math.sin(2 * math.pi * dt / 3.0)
            gyro[0] = 40 * math.sin(2 * math.pi * dt / 3.0)
        return tuple(accel), tuple(gyro)  # type: ignore[return-value]

    def height(self, now: float) -> float:
        """Radar target height: follows the simulated pelvis."""
        pelvis = next(j for j in self.skeleton(now) if j[0] == "pelvis")
        return pelvis[3] + (STAND_Z - STAND_POSE["pelvis"][2]) + self._rng.gauss(0, 0.01)

    def skeleton(self, now: float) -> list[tuple[str, float, float, float]]:
        """Fake 15-joint skeleton (name, x, y, z), z up. The person stands side-on to the radar at
        y≈1.5 m facing +x. Shape only, not a pose model."""
        dt = now - self.t0
        k = self.kind
        j = {n: list(v) for n, v in STAND_POSE.items()}
        lie = 0.0
        if k == "squat" and 0.0 <= dt < 3.0:
            _crouch(j, 0.55 * math.sin(math.pi * dt / 3.0))
        elif k == "wave" and 0.0 <= dt < 2.0:
            sh = j["r_sho"]
            j["r_elb"] = [sh[0] + 0.05, sh[1] + 0.1, sh[2] + 0.25]
            j["r_hand"] = [sh[0] + 0.05 + 0.18 * math.sin(2 * math.pi * 3 * dt), sh[1] + 0.15, sh[2] + 0.5]
        elif k == "fall_forward":
            lie = _ramp(dt, 0.0, 0.6, 1.5)
            _arms(j, (0.35, 0, 0.25), (0.35, 0, 0.25), lie)          # hands reach out to break the fall
            _crouch(j, 0.12 * math.sin(math.pi * lie))
            _topple(j, "x", +1, lie)
        elif k == "fall_backward":
            lie = _ramp(dt, 0.0, 0.65, 1.5)
            _arms(j, (-0.3, 0, 0.2), (-0.3, 0, 0.2), lie)
            _crouch(j, 0.2 * math.sin(math.pi * lie))
            _topple(j, "x", -1, lie)
        elif k == "fall_side":
            lie = _ramp(dt, 0.0, 0.55, 1.5)
            _arms(j, (0, -0.25, 0.35), (0, 0, 0), lie)              # lower arm goes out
            _topple(j, "y", -1, lie)
        elif k == "slip":
            slide = _ramp(dt, 0.0, 0.15)
            for n, d in (("l_foot", 0.55), ("r_foot", 0.55), ("l_knee", 0.35), ("r_knee", 0.35)):
                j[n][0] += d * slide
                j[n][2] += 0.15 * slide * (n.endswith("foot"))
            lie = _ramp(dt, 0.08, 0.48, 1.4)
            _arms(j, (0.15, 0, 0.45), (0.15, 0, 0.45), _ramp(dt, 0.0, 0.2))   # arms fly up
            _topple(j, "x", -1, lie, pivot=(0.4, 0.0))
        elif k == "faint":
            _crouch(j, 0.42 * _ramp(dt, 0.0, 0.9, 0.8), slump=True)        # knees buckle, body sinks
            lie = _ramp(dt, 0.9, 1.4, 1.5)
            _topple(j, "y", -1, lie, pivot=(0.0, 0.0))
        sway = 0.015 * math.sin(2 * math.pi * 0.3 * now) * (1 - lie)
        return [(n, round(v[0] + sway, 3), round(v[1] + 1.5, 3), round(v[2], 3)) for n, v in j.items()]

    def points(self, now: float, z: float, vz: float,
               joints: Optional[list] = None) -> list[tuple[float, float, float, float, float]]:
        """Fake point cloud (x, y, z, v, snr) sampled around the skeleton's bones, plus a little
        static clutter. Not a model of real radar returns."""
        r = self._rng
        jd = {k: (x, y, zz) for k, x, y, zz in (joints or self.skeleton(now))}
        top = max(p[2] for p in jd.values())
        pts = []
        for _ in range(r.randint(45, 70)):
            a, b, rad = r.choice(BONES_W)
            u = r.random()
            pa, pb = jd[a], jd[b]
            x, y, zz = (pa[i] + u * (pb[i] - pa[i]) + r.gauss(0, rad) for i in range(3))
            zz = max(0.0, zz)
            v = vz * (zz / max(top, 0.1)) + r.gauss(0, 0.05)
            pts.append((round(x, 3), round(y, 3), round(zz, 3), round(v, 3), round(r.uniform(10, 28), 1)))
        for _ in range(r.randint(4, 8)):    # static clutter: walls / fixtures
            pts.append((round(r.uniform(-1.2, 1.2), 3), round(r.choice((0.6, 2.6)) + r.gauss(0, 0.05), 3),
                        round(r.uniform(0.0, 1.8), 3), 0.0, round(r.uniform(3, 9), 1)))
        return pts


# Standing pose, metres; x forward/back, y left/right of the body, z up (feet at 0).
STAND_POSE = {
    "head": (0, 0, 1.66), "neck": (0, 0, 1.47),
    "l_sho": (0, -0.19, 1.42), "r_sho": (0, 0.19, 1.42),
    "l_elb": (0.02, -0.24, 1.14), "r_elb": (0.02, 0.24, 1.14),
    "l_hand": (0.05, -0.26, 0.88), "r_hand": (0.05, 0.26, 0.88),
    "pelvis": (0, 0, 0.96), "l_hip": (0, -0.1, 0.92), "r_hip": (0, 0.1, 0.92),
    "l_knee": (0.02, -0.11, 0.5), "r_knee": (0.02, 0.11, 0.5),
    "l_foot": (0, -0.12, 0.04), "r_foot": (0, 0.12, 0.04),
}
# (joint, joint, spread of points around that bone in m); torso listed twice so it gets more points
BONES_W = [("neck", "head", 0.07), ("neck", "pelvis", 0.11), ("neck", "pelvis", 0.11),
           ("l_sho", "r_sho", 0.06), ("l_sho", "l_elb", 0.04), ("l_elb", "l_hand", 0.04),
           ("r_sho", "r_elb", 0.04), ("r_elb", "r_hand", 0.04), ("l_hip", "r_hip", 0.07),
           ("l_hip", "l_knee", 0.06), ("l_knee", "l_foot", 0.05),
           ("r_hip", "r_knee", 0.06), ("r_knee", "r_foot", 0.05)]

UPPER = ("head", "neck", "l_sho", "r_sho", "l_elb", "r_elb", "l_hand", "r_hand")


def _crouch(j: dict, d: float, slump: bool = False) -> None:
    """Lower the body by d metres with bent knees; slump also folds the upper body forward."""
    for n in j:
        if n in ("l_foot", "r_foot"):
            continue
        j[n][2] -= d * (0.35 if n in ("l_knee", "r_knee") else 1.0)
    for n in ("l_knee", "r_knee"):
        j[n][0] += d * 0.6
    for n in ("l_hand", "r_hand"):
        j[n][0] += d * 0.4
    if slump:
        for n in UPPER:
            j[n][0] += d * 0.35
            j[n][2] -= d * 0.15


def _arms(j: dict, left: tuple, right: tuple, f: float) -> None:
    for side, off in (("l", left), ("r", right)):
        for n, w in ((f"{side}_elb", 0.5), (f"{side}_hand", 1.0)):
            for i in range(3):
                j[n][i] += off[i] * w * f


def _topple(j: dict, plane: str, sign: int, f: float, pivot: tuple = (0.0, 0.0)) -> None:
    """Rotate the body about a floor pivot by up to ~88°: plane 'x' tips forward/back, 'y' sideways."""
    if f <= 0:
        return
    th = sign * f * math.radians(88)
    c, s_ = math.cos(th), math.sin(th)
    i = 0 if plane == "x" else 1
    for n in j:
        d = j[n][i] - pivot[0]
        z = j[n][2] - pivot[1]
        j[n][i] = pivot[0] + d * c + z * s_
        j[n][2] = max(0.04, pivot[1] - d * s_ + z * c + 0.12 * f)


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
        mon.connected, mon.detail = True, "simulated data"
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
        self._last: Optional[tuple[float, float]] = None   # (t, z) for a rough vertical speed

    def make(self, now: float, wall: Optional[float] = None) -> RadarFrame:
        self.seq += 1
        z = self.scn.height(now)
        vz = 0.0
        if self._last is not None and now > self._last[0]:
            vz = (z - self._last[1]) / (now - self._last[0])
        self._last = (now, z)
        joints = self.scn.skeleton(now)
        pelvis = next(j for j in joints if j[0] == "pelvis")
        tg = RadarTarget(track_id=1, x=pelvis[1], y=1.5, z=z)
        return RadarFrame(seq=self.seq, t_pc=now, t_wall=time.time() if wall is None else wall,
                          targets=[tg], points=self.scn.points(now, z, vz, joints), cloud_kind="motion",
                          joints=joints, simulated=True)

    async def run(self) -> None:
        mon = self.sink.monitors[self.name]
        mon.connected, mon.detail = True, "simulated data"
        nxt = time.monotonic()
        while True:
            self.sink.on_radar(self.make(time.monotonic()))
            nxt += self.dt
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))
