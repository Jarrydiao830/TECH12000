"""执行逻辑：把一个已锁定的跌倒事件变成（至多一次）舵机动作。"""
from __future__ import annotations

import logging

from .actuators.base import ServoDriver
from .config import ServoCfg
from .models import DeployStatus, FallEvent, Mode
from .store import Store

log = logging.getLogger(__name__)


class Executor:
    def __init__(self, servo: ServoDriver, store: Store, cfg: ServoCfg):
        self.servo, self.store, self.cfg = servo, store, cfg

    def can_arm(self) -> tuple[bool, str]:
        """进入 ARMED 的前置条件。"""
        c = self.cfg
        if not self.servo.ready:
            return False, f"舵机控制器未就绪：{self.servo.detail}"
        if c.channel is None or c.release_pulse_us is None or c.move_time_ms is None:
            return False, "配置缺少 servo.channel / release_pulse_us / move_time_ms"
        if not self._pulse_ok(c.release_pulse_us):
            return False, "release_pulse_us 超出允许脉宽范围"
        return True, ""

    def _pulse_ok(self, pulse: int) -> bool:
        return self.cfg.pulse_min_us <= pulse <= self.cfg.pulse_max_us

    def execute(self, ev: FallEvent) -> DeployStatus:
        """同步执行（调用方放到工作线程）。同一 event_id 至多发一次指令。"""
        if ev.mode is Mode.MONITOR:
            return DeployStatus.NOT_SENT_MONITOR
        kind = "demo" if ev.mode is Mode.DEMO else "release"
        # 先落盘占位，再发指令。占位失败 = 以前处理过 = 绝不重发。
        if not self.store.claim_actuation(ev.event_id, kind):
            log.warning("事件 %s 已有执行记录，跳过", ev.event_id)
            return DeployStatus.SKIPPED_DUPLICATE
        c = self.cfg
        target = c.demo_pulse_us if ev.mode is Mode.DEMO else c.release_pulse_us
        try:
            if c.channel is None or target is None or c.move_time_ms is None:
                raise RuntimeError(f"配置缺少 {kind} 动作所需的 channel/脉宽/时间")
            if not self._pulse_ok(target):
                raise RuntimeError(f"目标脉宽 {target}us 超出 [{c.pulse_min_us},{c.pulse_max_us}]")
            acked = self.servo.move(c.channel, target, c.move_time_ms)
        except Exception as e:  # 发送失败也不重试：是否再次动作由人决定
            log.error("执行指令失败: %s", e)
            self.store.finish_actuation(ev.event_id, f"send_failed: {e}")
            ev.detail["actuation_error"] = str(e)
            return DeployStatus.SEND_FAILED
        if ev.mode is Mode.DEMO:
            status = DeployStatus.DEMO_SENT
        else:
            status = DeployStatus.CONTROLLER_ACKED if acked else DeployStatus.COMMAND_SENT
        self.store.finish_actuation(ev.event_id, status.value)
        return status
