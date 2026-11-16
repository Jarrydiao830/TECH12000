"""融合状态机（第一版基线规则，可解释，但【尚未经实验验证】）。

  Initializing --数据源全部新鲜并稳定--> Ready
  Ready        --手环或雷达任一候选------> Suspected Fall
  Suspected    --两路候选在 coincidence_s 内吻合--> Triggered（锁定，直到人工复位）
  Suspected    --超时无新证据------------> Ready
  任意(除Triggered) --必需数据源过期/断联--> Fault --恢复并稳定--> Ready

仅手环剧烈运动最多到 Suspected，不会单独触发。
"两路候选时间吻合"只是起点基线，不代表已验证算法；需用挥手、洗头、弯腰、
蹲下、坐下、捡东西等动作的实录数据通过离线回放评估误报/漏报/提前量后再迭代。
"""
from __future__ import annotations

from typing import Optional

from ..config import FusionCfg
from ..models import ImuSample, RadarFrame, SystemState
from .features import RadarFeatures, WristFeatures


class FusionStateMachine:
    def __init__(self, cfg: FusionCfg):
        self.cfg = cfg
        self.wrist = WristFeatures(cfg.wrist)
        self.radar = RadarFeatures(cfg.radar)
        self.state = SystemState.INITIALIZING
        self.reason = "启动"
        self._last_evidence: Optional[float] = None
        self.trigger_detail: dict = {}

    def reset(self) -> None:
        self.wrist.reset()
        self.radar.reset()
        self.state = SystemState.INITIALIZING
        self.reason = "复位"
        self._last_evidence = None
        self.trigger_detail = {}

    def on_imu(self, s: ImuSample) -> None:
        self.wrist.update(s)

    def on_radar(self, f: RadarFrame) -> None:
        self.radar.update(f)

    def _set(self, state: SystemState, reason: str, out: list) -> None:
        if state is not self.state:
            out.append((self.state, state, reason))
            self.state, self.reason = state, reason

    def step(self, now: float, sources_fresh: bool, settled: bool, fault_reason: str = "") -> list:
        """推进状态机，返回本步发生的转移列表 [(from, to, reason), ...]。"""
        out: list = []
        S = SystemState
        if self.state is S.TRIGGERED:
            return out   # 锁定：只有人工复位能离开
        if self.state in (S.INITIALIZING, S.FAULT):
            if settled:
                self._set(S.READY, "数据源正常", out)
            elif not sources_fresh and fault_reason:
                self._set(S.FAULT, fault_reason, out)
            if self.state is not S.READY:
                return out
        if not sources_fresh:
            self._set(S.FAULT, fault_reason or "数据过期", out)
            return out

        wc = self.wrist.candidate(now)
        rc = self.radar.candidate(now)
        if wc is not None or rc is not None:
            self._last_evidence = now
            if self.state is S.READY:
                which = "手环+雷达" if (wc is not None and rc is not None) else ("手环" if wc is not None else "雷达")
                self._set(S.SUSPECTED_FALL, f"{which}出现异常特征", out)
        if self.state is S.SUSPECTED_FALL:
            if wc is not None and rc is not None and abs(wc - rc) <= self.cfg.coincidence_s:
                self.trigger_detail = {
                    "rule": "baseline_wrist_and_radar_coincidence",
                    "validated": False,
                    "wrist_candidate_t": wc,
                    "radar_candidate_t": rc,
                    "radar_height_drop_m": self.radar.height_drop,
                }
                self._set(S.TRIGGERED, "手环与雷达候选在时间窗内吻合（基线规则）", out)
            elif self._last_evidence is None or now - self._last_evidence > self.cfg.suspect_timeout_s:
                self._set(S.READY, "疑似状态超时，无进一步证据", out)
        return out

    def features_snapshot(self) -> dict:
        r = lambda v: None if v is None else round(v, 3)
        return {
            "wrist": {"accel_mag": r(self.wrist.accel_mag), "gyro_mag": r(self.wrist.gyro_mag),
                      "jerk": r(self.wrist.jerk)},
            "radar": {"height": r(self.radar.height), "height_drop": r(self.radar.height_drop),
                      "in_zone": self.radar.in_zone, "has_height": self.radar.has_height,
                      "n_points": self.radar.n_points, "points_unusable": self.radar.points_unusable},
        }
