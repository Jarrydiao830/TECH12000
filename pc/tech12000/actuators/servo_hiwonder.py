"""幻尔 Hiwonder 16路舵机控制器驱动 —— 【未实现，等待官方资料】。

故意不写任何帧格式：这块板不是 Pololu Maestro，不能套用 Maestro 协议，
也不凭记忆套用幻尔其他型号的协议。拿到这块板的手册/通信示例后需要确认：

  1. 电脑端连接方式：USB HID 还是 USB 虚拟串口？macOS 下如何枚举？
  2. 位置指令帧格式、通道编号从 0 还是 1 开始、脉宽单位与范围。
  3. 是否有应答/确认帧（决定 supports_ack，界面才能显示"控制器确认接收"）。
  4. 板载供电通路的电压范围和电流能力，与 X70S 峰值电流是否匹配；信号共地要求。
  5. 上电时各通道的默认输出行为（避免上电瞬间舵机乱动）。
"""
from __future__ import annotations

from typing import Optional

from .base import ServoDriver


class HiwonderServo(ServoDriver):
    name = "hiwonder"
    supports_ack = False   # 待协议确认

    def __init__(self, port: Optional[str]):
        self.port = port

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return "Hiwonder 驱动未实现：等待官方手册与通信协议"

    def move(self, channel: int, pulse_us: int, time_ms: int) -> Optional[bool]:
        raise NotImplementedError(self.detail)
