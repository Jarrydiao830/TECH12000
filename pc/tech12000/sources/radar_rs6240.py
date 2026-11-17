"""RS6240 雷达数据源：经开发板 USB 串口（CH347T）读取 HIF 点云。

前提（见 docs/open_items.md 的 RS6240 一节）：
  - 雷达烧录了 HIF 走 UART 的固件，例如厂家 HostSample 附带的
    Tracking_uart_mrs6240_p2512.img；出厂 Sample 固件的 HIF 走 SPI，Mac 读不到。
  - 底板拨码把雷达 UART0 接到 Type-C；sources.radar.port 指向对应的 /dev/cu.*。
  - 波特率默认 1 Mbps（厂家 ESP32 主机示例的 UART 预设），以实测为准。

本驱动只监听，不向雷达发送任何命令。如果固件要求主机先唤醒/轮询才上报，
`tech12000 radar-probe` 会看到 0 帧，需要按 HIF 手册补充轮询逻辑。

只有笛卡尔坐标点云会转成 RadarFrame.points；极坐标点云的轴向约定文档未给出，
不做换算，只计数。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

from ..config import SourceCfg
from ..models import RadarFrame
from .rs6240_hif import MSG_HEARTBEAT, MSG_POINT_CLOUD, MSG_STARTUP, C3Reassembler, HifStreamParser, PointCloud

log = logging.getLogger(__name__)


class Rs6240Decoder:
    """字节流 -> 点云。与串口解耦，便于测试和离线分析。"""

    def __init__(self) -> None:
        self.parser = HifStreamParser()
        self.c3 = C3Reassembler()
        self.counts: dict[str, int] = {"heartbeat": 0, "startup": 0, "polar_frames": 0, "other_msgs": 0}
        self.last_kinds: dict[str, int] = {}

    def feed(self, data: bytes) -> list[PointCloud]:
        out = []
        for fr in self.parser.feed(data):
            if fr.msg_id == MSG_POINT_CLOUD:
                pc = self.c3.feed(fr.payload)
                if pc is not None:
                    self.last_kinds[pc.kind] = self.last_kinds.get(pc.kind, 0) + 1
                    if not pc.cartesian:
                        self.counts["polar_frames"] += 1
                    out.append(pc)
            elif fr.msg_id == MSG_HEARTBEAT:
                self.counts["heartbeat"] += 1
            elif fr.msg_id == MSG_STARTUP:
                self.counts["startup"] += 1
            else:
                self.counts["other_msgs"] += 1
        return out

    def stats(self) -> dict:
        return {"hif": dict(self.parser.stats), "c3": dict(self.c3.stats), **self.counts,
                "kinds": dict(self.last_kinds)}


class Rs6240Radar:
    name = "radar"

    def __init__(self, sink, cfg: SourceCfg):
        self.sink, self.cfg = sink, cfg
        self._stop = threading.Event()
        self.decoder = Rs6240Decoder()
        self._seq = 0

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        th = threading.Thread(target=self._reader, args=(loop,), name="radar-serial", daemon=True)
        th.start()
        try:
            await asyncio.Event().wait()
        finally:
            self._stop.set()

    def _set_conn(self, ok: bool, detail: str) -> None:
        mon = self.sink.monitors[self.name]
        mon.connected, mon.detail = ok, detail

    def _reader(self, loop: asyncio.AbstractEventLoop) -> None:
        import serial  # pyserial

        while not self._stop.is_set():
            if not self.cfg.port:
                loop.call_soon_threadsafe(self._set_conn, False, "sources.radar.port not configured")
                time.sleep(2)
                continue
            try:
                ser = serial.Serial(self.cfg.port, self.cfg.baud, timeout=0.05)
            except Exception as e:
                loop.call_soon_threadsafe(self._set_conn, False, f"Cannot open serial port: {e}")
                time.sleep(1)
                continue
            self.decoder = Rs6240Decoder()      # 重连后从头找帧，不拼接断开前的半帧
            loop.call_soon_threadsafe(self._set_conn, True, f"Opened {self.cfg.port} @ {self.cfg.baud}")
            try:
                while not self._stop.is_set():
                    data = ser.read(4096)
                    if not data:
                        continue
                    t_pc, t_wall = time.monotonic(), time.time()
                    for pc in self.decoder.feed(data):
                        loop.call_soon_threadsafe(self._emit, pc, t_pc, t_wall)
            except Exception as e:
                loop.call_soon_threadsafe(self._set_conn, False, f"Serial port disconnected: {e}")
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(0.5)

    def _emit(self, pc: PointCloud, t_pc: float, t_wall: float) -> None:
        self._seq += 1
        pts = pc.points if pc.cartesian else None
        self.sink.on_radar(RadarFrame(seq=self._seq, t_pc=t_pc, t_wall=t_wall, points=pts,
                                      device_frame=pc.frame_idx, cloud_kind=pc.kind))

    def status(self, now_pc: float) -> dict:
        return self.decoder.stats()
