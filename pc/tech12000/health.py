"""链路健康：序号连续性、重复包、丢包、数据新鲜度。"""
from __future__ import annotations

from typing import Optional


class LinkMonitor:
    def __init__(self, name: str, stale_timeout_s: float):
        self.name = name
        self.stale_timeout_s = stale_timeout_s
        self.connected = False          # 传输层（串口/USB）是否打开
        self.detail = ""                # 人可读的故障说明
        self.last_rx_pc: Optional[float] = None
        self.last_rx_wall: Optional[float] = None
        self.received = 0
        self.lost = 0
        self.duplicates = 0
        self.out_of_order = 0
        self.session_changes = 0
        self._session: Optional[int] = None
        self._last_seq: Optional[int] = None
        self._fresh_since: Optional[float] = None

    def on_packet(self, session_id: Optional[int], seq: Optional[int], t_pc: float, t_wall: float) -> bool:
        """登记一个包。返回 False 表示重复/乱序旧包，调用方应丢弃。"""
        if session_id != self._session:
            if self._session is not None:
                self.session_changes += 1
            self._session, self._last_seq = session_id, None
        if seq is not None and self._last_seq is not None:
            if seq == self._last_seq:
                self.duplicates += 1
                return False
            if seq < self._last_seq:
                self.out_of_order += 1
                return False
            self.lost += seq - self._last_seq - 1
        self._last_seq = seq if seq is not None else self._last_seq
        if self.last_rx_pc is None or (t_pc - self.last_rx_pc) > self.stale_timeout_s:
            self._fresh_since = t_pc
        self.last_rx_pc, self.last_rx_wall = t_pc, t_wall
        self.received += 1
        return True

    def age(self, now_pc: float) -> Optional[float]:
        return None if self.last_rx_pc is None else now_pc - self.last_rx_pc

    def is_fresh(self, now_pc: float) -> bool:
        a = self.age(now_pc)
        return a is not None and a <= self.stale_timeout_s

    def fresh_duration(self, now_pc: float) -> float:
        if not self.is_fresh(now_pc) or self._fresh_since is None:
            return 0.0
        return now_pc - self._fresh_since

    def snapshot(self, now_pc: float) -> dict:
        total = self.received + self.lost
        a = self.age(now_pc)
        return {
            "name": self.name,
            "connected": self.connected,
            "fresh": self.is_fresh(now_pc),
            "age_s": None if a is None else round(a, 3),
            "last_rx_wall": self.last_rx_wall,
            "received": self.received,
            "lost": self.lost,
            "loss_rate": round(self.lost / total, 4) if total else None,
            "duplicates": self.duplicates,
            "out_of_order": self.out_of_order,
            "session_changes": self.session_changes,
            "detail": self.detail,
        }
