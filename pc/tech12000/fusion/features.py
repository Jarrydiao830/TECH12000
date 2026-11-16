"""特征提取。

注意事项（来自项目约束，写在代码旁以免遗忘）：
  - 手腕运动不能直接代表躯干姿态。
  - 雷达径向速度不能直接当作垂直速度：这里的下降量只由连续位置估计得出。
  - 点云中心不能直接当作人体质心：这里只使用固件给出的跟踪目标，
    若固件不输出目标高度，雷达候选条件将永远不成立，并在状态里注明。
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from ..config import RadarRuleCfg, WristCfg
from ..models import ImuSample, RadarFrame, RadarTarget


class WristFeatures:
    def __init__(self, cfg: WristCfg):
        self.cfg = cfg
        self._buf: deque[tuple[float, float, float]] = deque()  # (t, |a|, |w|)
        self.accel_mag: Optional[float] = None
        self.gyro_mag: Optional[float] = None
        self.jerk: Optional[float] = None   # d|a|/dt, m/s^3

    def reset(self) -> None:
        self._buf.clear()
        self.accel_mag = self.gyro_mag = self.jerk = None

    def update(self, s: ImuSample) -> None:
        t = s.t_est if s.t_est is not None else s.t_pc
        a = math.sqrt(sum(v * v for v in s.accel))
        g = math.sqrt(sum(v * v for v in s.gyro))
        if self._buf:
            dt = t - self._buf[-1][0]
            self.jerk = (a - self._buf[-1][1]) / dt if dt > 1e-4 else self.jerk
        self.accel_mag, self.gyro_mag = a, g
        self._buf.append((t, a, g))

    def _trim(self, now: float) -> None:
        lim = now - self.cfg.window_s
        while self._buf and self._buf[0][0] < lim:
            self._buf.popleft()

    def candidate(self, now: float) -> Optional[float]:
        """窗口内同时出现(冲击或失重)与高角速度时，返回加速度异常的最近时刻。"""
        self._trim(now)
        if not self._buf:
            return None
        t_acc = None
        gyro_hit = False
        for t, a, g in self._buf:
            if a >= self.cfg.impact_accel_ms2 or a <= self.cfg.freefall_accel_ms2:
                t_acc = t
            if g >= self.cfg.gyro_dps:
                gyro_hit = True
        return t_acc if (t_acc is not None and gyro_hit) else None


class RadarFeatures:
    def __init__(self, cfg: RadarRuleCfg):
        self.cfg = cfg
        self._buf: deque[tuple[float, float]] = deque()  # (t, z)
        self.height: Optional[float] = None
        self.height_drop: Optional[float] = None
        self.in_zone: Optional[bool] = None
        self.has_height = False    # 固件是否实际给出了目标高度

    def reset(self) -> None:
        self._buf.clear()
        self.height = self.height_drop = self.in_zone = None

    def _in_zone(self, tg: RadarTarget) -> bool:
        z = self.cfg.zone
        if z is None:
            return True
        for rng, v in ((z.x, tg.x), (z.y, tg.y)):
            if rng is not None and (v is None or not (rng[0] <= v <= rng[1])):
                return False
        return True

    def update(self, f: RadarFrame) -> None:
        t = f.t_est if f.t_est is not None else f.t_pc
        # 第一版单人监测：取区域内第一个带高度的目标
        tg = next((x for x in f.targets if x.z is not None and self._in_zone(x)), None)
        self.in_zone = tg is not None if f.targets else None
        if tg is None:
            self.height = None
            return
        self.has_height = True
        self.height = tg.z
        self._buf.append((t, tg.z))

    def _trim(self, now: float) -> None:
        lim = now - self.cfg.window_s
        while self._buf and self._buf[0][0] < lim:
            self._buf.popleft()

    def candidate(self, now: float) -> Optional[float]:
        """窗口内高度下降量达到阈值时，返回最低点时刻。"""
        self._trim(now)
        if len(self._buf) < self.cfg.min_track_frames:
            self.height_drop = None
            return None
        t_last, z_last = self._buf[-1]
        z_max = max(z for _, z in self._buf)
        self.height_drop = z_max - z_last
        return t_last if self.height_drop >= self.cfg.height_drop_m else None
