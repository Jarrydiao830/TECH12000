"""执行器接口与模拟实现。"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from ..config import LedCfg, ServoCfg
from ..models import Mode, SystemState

log = logging.getLogger(__name__)


class ServoDriver:
    """舵机控制器驱动接口。"""

    name = "base"
    supports_ack = False     # 协议是否提供"控制器已接收"确认
    simulated = False

    def open(self) -> None: ...
    def close(self) -> None: ...

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return ""

    def move(self, channel: int, pulse_us: int, time_ms: int) -> Optional[bool]:
        """发送位置指令。返回 True=控制器确认；None=已发送但协议无确认；失败抛异常。"""
        raise NotImplementedError

    def status(self) -> dict:
        return {"driver": self.name, "connected": self.ready, "supports_ack": self.supports_ack,
                "simulated": self.simulated, "detail": self.detail}


class SimServo(ServoDriver):
    name = "sim"
    simulated = True

    def __init__(self) -> None:
        self.moves: list[tuple[float, int, int, int]] = []

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return "Simulated servo, drives no hardware"

    def move(self, channel: int, pulse_us: int, time_ms: int) -> Optional[bool]:
        self.moves.append((time.time(), channel, pulse_us, time_ms))
        log.info("[SimServo] ch=%s pulse=%sus time=%sms", channel, pulse_us, time_ms)
        return None


class NoServo(ServoDriver):
    name = "none"

    @property
    def detail(self) -> str:
        return "No servo controller configured"


class LedDriver:
    name = "base"

    def set_state(self, state: SystemState, mode: Mode) -> None: ...

    def status(self) -> dict:
        return {"driver": self.name}


class SimLed(LedDriver):
    name = "sim"

    def __init__(self) -> None:
        self.last: Optional[tuple[str, str]] = None

    def set_state(self, state: SystemState, mode: Mode) -> None:
        self.last = (state.value, mode.value)

    def status(self) -> dict:
        return {"driver": self.name, "last": self.last}


class ReceiverLed(LedDriver):
    """经固定端 ESP32 控制 LED：向接收板串口发一行 JSON 指令（见 docs/protocol.md）。"""
    name = "receiver"

    def __init__(self, send: Callable[[dict], bool]):
        self._send = send
        self.last_ok: Optional[bool] = None

    def set_state(self, state: SystemState, mode: Mode) -> None:
        self.last_ok = self._send({"t": "led", "state": state.value, "mode": mode.value})

    def status(self) -> dict:
        return {"driver": self.name, "last_send_ok": self.last_ok}


def make_servo(cfg: ServoCfg) -> ServoDriver:
    if cfg.driver == "sim":
        return SimServo()
    if cfg.driver == "hiwonder":
        from .servo_hiwonder import HiwonderServo
        return HiwonderServo(cfg.port)
    if cfg.driver == "none":
        return NoServo()
    raise ValueError(f"Unknown servo driver: {cfg.driver}")


def make_led(cfg: LedCfg, receiver_send: Optional[Callable[[dict], bool]] = None) -> LedDriver:
    if cfg.driver == "sim":
        return SimLed()
    if cfg.driver == "receiver":
        if receiver_send is None:
            raise ValueError("led.driver=receiver requires sources.wristband.driver=serial")
        return ReceiverLed(receiver_send)
    if cfg.driver == "none":
        return LedDriver()
    raise ValueError(f"Unknown LED driver: {cfg.driver}")
