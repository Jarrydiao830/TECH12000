"""设备时钟 -> 电脑 monotonic 时基 的偏差估计。

不同设备的时钟不能直接比较；"电脑同时收到"也不等于"同时采样"。
做法：对每个 (设备, session)，offset = t_pc - t_device 的滑动窗口最小值。
传输延迟只会让 t_pc 变晚，所以最小值最接近"真实偏差 + 最小链路延迟"。
最小链路延迟本身无法仅靠单向数据消除，需另做端到端延迟实验标定。
"""
from __future__ import annotations

from collections import deque
from typing import Optional


class ClockOffsetEstimator:
    def __init__(self, window: int = 500):
        self._window = window
        self._key: Optional[tuple] = None
        self._buf: deque[float] = deque(maxlen=window)

    def update(self, key: tuple, t_device_s: float, t_pc: float) -> float:
        """喂入一对时间，返回估计的采样时刻（电脑 monotonic 时基）。"""
        if key != self._key:        # 设备重启/换 session：旧偏差作废
            self._key = key
            self._buf.clear()
        self._buf.append(t_pc - t_device_s)
        return t_device_s + min(self._buf)

    @property
    def offset(self) -> Optional[float]:
        return min(self._buf) if self._buf else None

    def latency_estimate(self, t_device_s: float, t_pc: float) -> Optional[float]:
        """该包相对窗口内最快包的额外延迟（秒），用于监视积压。"""
        off = self.offset
        return None if off is None else (t_pc - t_device_s) - off
