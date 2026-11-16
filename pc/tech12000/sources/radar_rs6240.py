"""RS6240 雷达数据源 —— 【未实现，等待官方SDK/协议文档】。

故意不写任何帧解析：不能假定它是普通文本串口，也不能假定输出全部跟踪字段。
拿到《MRS6240-AIP-DEV-V1 使用手册》和 RS6x_7x_mmWave_sdk 后需要确认：

  1. 底板 USB 上有哪两个串口芯片（官网写"驱动有两个，均需安装"），macOS 是否有驱动，
     哪个口是数据口、哪个是调试/烧录口，波特率多少。
  2. 出厂/示例固件输出什么：点云？跟踪目标？是否含高度(z)？帧率？帧头/长度/校验？
  3. 坐标系定义与安装姿态要求（决定 fusion.radar.zone 和"高度"的含义）。
  4. 帧内是否带设备时间戳或帧号（用于丢帧统计和时间对齐）。
  5. 是否需要先下发配置命令才开始输出；换固件是否必须用 Windows 版 CDK。

实现后应产出 models.RadarFrame；固件不提供的字段保持 None。
"""
from __future__ import annotations

import asyncio

from ..config import SourceCfg


class Rs6240Radar:
    name = "radar"

    def __init__(self, sink, cfg: SourceCfg):
        self.sink, self.cfg = sink, cfg

    async def run(self) -> None:
        mon = self.sink.monitors[self.name]
        mon.connected = False
        mon.detail = "RS6240 驱动未实现：等待官方SDK与数据协议"
        await asyncio.Event().wait()
