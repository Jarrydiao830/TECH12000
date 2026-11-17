"""核心引擎：接收数据 -> 时间对齐 -> 特征/状态机 -> 事件 -> 执行，全部在本机完成。

界面、手机、APNs 都只是 listeners 的订阅者；它们卡住或断开不影响这里。
引擎只依赖传入的时间戳，不自己读时钟，因此实时运行与离线回放走同一套逻辑。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from typing import Callable, Optional

from .actuators.base import LedDriver, ServoDriver
from .config import Config
from .executor import Executor
from .fusion.state_machine import FusionStateMachine
from .health import LinkMonitor
from .models import (DEPLOY_OUTCOME_UNKNOWN, DeployStatus, FallEvent, ImuSample, Mode,
                     RadarFrame, SystemState)
from .store import Store
from .timebase import ClockOffsetEstimator

log = logging.getLogger(__name__)

ARM_CONFIRM = "ARM"
INIT_TIMEOUT_S = 5.0


class Engine:
    def __init__(self, cfg: Config, store: Store, servo: ServoDriver, led: LedDriver,
                 recorder, inline_actuation: bool = False):
        self.cfg, self.store, self.servo, self.led, self.rec = cfg, store, servo, led, recorder
        self.executor = Executor(servo, store, cfg.actuators.servo)
        self.fsm = FusionStateMachine(cfg.fusion)
        self.monitors = {
            "wristband": LinkMonitor("wristband", cfg.sources.wristband.stale_timeout_s),
            "radar": LinkMonitor("radar", cfg.sources.radar.stale_timeout_s),
        }
        self.mode = Mode.MONITOR          # 每次启动都从未使能开始
        self.monitoring = True
        self.listeners: list[Callable[[str, dict], None]] = []
        self.status_providers: dict[str, Callable[[float], dict]] = {}
        self.on_reset_hooks: list[Callable[[], None]] = []
        self.last_event: Optional[FallEvent] = None
        self.live_imu: deque = deque(maxlen=600)   # 界面曲线用
        self.live_n = 0
        self.last_radar: Optional[RadarFrame] = None
        self.last_latency: Optional[float] = None
        self._wrist_clock = ClockOffsetEstimator()
        self._inline = inline_actuation
        self._t_start: Optional[float] = None
        self._now = 0.0
        self._sim_input = False
        self._tasks: set = set()
        self._led_key = None

    # ------------------------------------------------------------ 输入
    def on_imu(self, s: ImuSample) -> None:
        mon = self.monitors["wristband"]
        if not mon.on_packet(s.session_id, s.seq, s.t_pc, s.t_wall):
            return   # 重复/乱序旧包不进入判断
        if s.t_mcu_us is not None:
            key = (s.device_id, s.session_id)
            dev_s = s.t_mcu_us / 1e6
            s.t_est = self._wrist_clock.update(key, dev_s, s.t_pc)
            self.last_latency = self._wrist_clock.latency_estimate(dev_s, s.t_pc)
        self._sim_input = self._sim_input or s.simulated
        self.rec.write("imu", s.to_dict())
        self.live_imu.append((s.t_wall, *s.accel, *s.gyro))
        self.live_n += 1
        if self.monitoring:
            self.fsm.on_imu(s)
        self.tick(s.t_pc, s.t_wall)

    def on_radar(self, f: RadarFrame) -> None:
        mon = self.monitors["radar"]
        if not mon.on_packet(None, f.seq, f.t_pc, f.t_wall):
            return
        self._sim_input = self._sim_input or f.simulated
        self.rec.write("radar", f.to_dict())
        self.last_radar = f
        if self.monitoring:
            self.fsm.on_radar(f)
        self.tick(f.t_pc, f.t_wall)

    def on_raw(self, src: str, line: str, t_pc: float, t_wall: float) -> None:
        self.rec.write("raw", {"src": src, "line": line, "t_pc": t_pc, "t_wall": t_wall})

    def on_button(self, o: dict, t_pc: float, t_wall: float) -> None:
        # 实体按钮只上报并记录；是否映射为复位由后续决定，绝不映射为使能。
        self.rec.write("button", {"msg": o, "t_pc": t_pc, "t_wall": t_wall})
        self._emit("button", {"msg": o, "t_wall": t_wall})

    # ------------------------------------------------------------ 推进
    def tick(self, now: float, wall: float) -> None:
        """周期调用（也在每个数据包后调用）。数据全断时靠它发现超时。"""
        self._now = now
        if self._t_start is None:
            self._t_start = now
        req = self.cfg.sources.required
        stale = [n for n in req if not self.monitors[n].is_fresh(now)]
        fresh = not stale
        settle = self.cfg.fusion.init_settle_s
        settled = fresh and all(self.monitors[n].fresh_duration(now) >= settle for n in req)
        reason = ""
        if stale and (self.fsm.state is not SystemState.INITIALIZING
                      or now - self._t_start > INIT_TIMEOUT_S):
            parts = []
            for n in stale:
                m = self.monitors[n]
                parts.append(f"{n}: " + (m.detail if not m.connected and m.detail else
                                          "no data" if m.last_rx_pc is None else "stale data"))
            reason = "；".join(parts)
        if not self.monitoring:
            return
        for frm, to, why in self.fsm.step(now, fresh, settled, reason):
            self._on_transition(frm, to, why, now, wall)
        self._update_led()

    def _on_transition(self, frm, to, why, now, wall) -> None:
        log.info("State %s -> %s (%s)", frm.value, to.value, why)
        payload = {"from": frm.value, "to": to.value, "reason": why, "t_pc": now, "t_wall": wall,
                   "mode": self.mode.value}
        self.rec.write("state", payload)
        self._emit("state", payload)
        if to is SystemState.TRIGGERED:
            self._create_event(wall)

    def _create_event(self, wall: float) -> None:
        ev = FallEvent(event_id=uuid.uuid4().hex, t_wall=wall, mode=self.mode,
                       simulated_input=self._sim_input, detail=dict(self.fsm.trigger_detail))
        self.last_event = ev
        self.store.save_event(ev)            # 先持久化事件，再做任何动作
        self.rec.write("event", ev.to_dict())
        if self._inline:
            self._finish_event(ev, self.executor.execute(ev))
        else:
            t = asyncio.get_running_loop().create_task(self._run_actuation(ev))
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)

    async def _run_actuation(self, ev: FallEvent) -> None:
        # 舵机/串口 IO 放到线程，避免阻塞数据处理
        try:
            status = await asyncio.get_running_loop().run_in_executor(None, self.executor.execute, ev)
        except Exception as e:
            log.exception("Execution error")
            ev.detail["actuation_error"] = str(e)
            status = DeployStatus.SEND_FAILED
        self._finish_event(ev, status)

    def _finish_event(self, ev: FallEvent, status: DeployStatus) -> None:
        ev.deploy_status = status
        self.store.save_event(ev)
        self.rec.write("actuation", {"event_id": ev.event_id, "status": status.value,
                                     "mode": ev.mode.value})
        self._emit("event", ev.to_dict())    # 本地执行完成后才异步通知界面/手机

    def _update_led(self) -> None:
        key = (self.fsm.state, self.mode)
        if key != self._led_key:
            self._led_key = key
            try:
                self.led.set_state(*key)
            except Exception:
                log.exception("LED command failed")

    def _emit(self, kind: str, payload: dict) -> None:
        for fn in self.listeners:
            try:
                fn(kind, payload)
            except Exception:
                log.exception("Listener error")

    # ------------------------------------------------------------ 操作员控制（仅本机界面可调用）
    def set_mode(self, mode: Mode, confirm: str = "") -> tuple[bool, str]:
        if self.fsm.state is SystemState.TRIGGERED:
            return False, "Event is latched. Check on site and reset first."
        if mode is Mode.ARMED:
            if confirm != ARM_CONFIRM:
                return False, f"Entering ARMED needs explicit confirmation (confirm='{ARM_CONFIRM}')"
            if self.fsm.state is not SystemState.READY:
                return False, "Can only arm in the Ready state"
            ok, why = self.executor.can_arm()
            if not ok:
                return False, why
        self.mode = mode
        self.rec.write("mode", {"mode": mode.value, "t_pc": self._now})
        self._emit("mode", {"mode": mode.value})
        self._update_led()
        return True, ""

    def reset(self) -> None:
        """人工复位：回到未使能状态，不自动重新使能。不移动舵机。"""
        self.mode = Mode.MONITOR
        self.fsm.reset()
        self._t_start = None
        self._sim_input = False
        for h in self.on_reset_hooks:
            h()
        self.rec.write("reset", {"t_pc": self._now})
        self._emit("reset", {})
        self._update_led()

    def set_monitoring(self, on: bool) -> None:
        if on == self.monitoring:
            return
        self.monitoring = on
        if not on:                      # 停止监测同时撤销使能
            if self.fsm.state is not SystemState.TRIGGERED:
                self.fsm.reset()
            self.mode = Mode.MONITOR
        self._t_start = None
        self.rec.write("monitoring", {"on": on, "t_pc": self._now})
        self._emit("monitoring", {"on": on})

    # ------------------------------------------------------------ 状态快照
    def status(self, wall: float) -> dict:
        now = self._now
        devices = {n: m.snapshot(now) for n, m in self.monitors.items()}
        devices["servo"] = self.servo.status()
        for name, fn in self.status_providers.items():
            devices[name] = fn(now)
        ev = self.last_event
        return {
            "server_time": wall,
            "state": self.fsm.state.value,
            "state_reason": self.fsm.reason,
            "mode": self.mode.value,
            "monitoring": self.monitoring,
            "devices": devices,
            "led": self.led.status(),
            "features": self.fsm.features_snapshot(),
            "wrist_extra_latency_ms": None if self.last_latency is None else round(self.last_latency * 1e3, 1),
            "deploy_status": ev.deploy_status.value if ev else DeployStatus.NONE.value,
            "deploy_outcome": DEPLOY_OUTCOME_UNKNOWN if ev else None,
            "last_event": ev.to_dict() if ev else None,
            "config_version": self.cfg.version_hash(),
            "recorder_dropped": self.rec.dropped,
            "simulated_input": self._sim_input,
        }
