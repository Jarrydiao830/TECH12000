"""手环数据源：固定端 ESP32-S3 的 USB 串口。

线路协议是本项目自己的固件定义的（docs/protocol.md），每行一个 JSON 对象。
串口读取在独立线程，解析后的对象投递回 asyncio 事件循环；断开后自动重连。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Optional

from ..config import SourceCfg
from ..models import ImuSample

log = logging.getLogger(__name__)

FLAG_IMU_TIME_VALID = 0x01
FLAG_SIMULATED = 0x02
FLAG_IMU_FAULT = 0x04


def parse_imu_line(o: dict, t_pc: float, t_wall: float) -> ImuSample:
    """把接收板的一条 imu 消息转成 ImuSample。字段缺失/类型错误会抛异常。"""
    flags = int(o.get("f", 0))
    a, g = o["a"], o["g"]
    if len(a) != 3 or len(g) != 3:
        raise ValueError("a/g 长度必须为3")
    return ImuSample(
        device_id=str(o["dev"]), session_id=int(o["ses"]), seq=int(o["seq"]),
        accel=(float(a[0]), float(a[1]), float(a[2])),
        gyro=(float(g[0]), float(g[1]), float(g[2])),
        t_pc=t_pc, t_wall=t_wall,
        t_mcu_us=int(o["tm"]),
        t_imu_us=int(o["ti"]) if (flags & FLAG_IMU_TIME_VALID and o.get("ti") is not None) else None,
        t_board_us=int(o["trx"]) if o.get("trx") is not None else None,
        flags=flags, rssi=o.get("rssi"), simulated=bool(flags & FLAG_SIMULATED))


class SerialWristband:
    name = "wristband"

    def __init__(self, sink, cfg: SourceCfg):
        self.sink, self.cfg = sink, cfg
        self._ser = None
        self._wlock = threading.Lock()
        self._stop = threading.Event()
        self.board: dict = {"connected": False, "detail": "未连接", "heartbeat": None,
                            "last_hb_pc": None, "parse_errors": 0}

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        th = threading.Thread(target=self._reader, args=(loop,), name="wrist-serial", daemon=True)
        th.start()
        try:
            await asyncio.Event().wait()
        finally:
            self._stop.set()

    def _set_conn(self, ok: bool, detail: str) -> None:
        self.board["connected"], self.board["detail"] = ok, detail
        mon = self.sink.monitors[self.name]
        mon.connected, mon.detail = ok, detail

    def _reader(self, loop: asyncio.AbstractEventLoop) -> None:
        import serial  # pyserial

        while not self._stop.is_set():
            if not self.cfg.port:
                loop.call_soon_threadsafe(self._set_conn, False, "未配置 sources.wristband.port")
                time.sleep(2)
                continue
            try:
                ser = serial.Serial(self.cfg.port, self.cfg.baud, timeout=0.2)
            except Exception as e:
                loop.call_soon_threadsafe(self._set_conn, False, f"打不开串口: {e}")
                time.sleep(1)
                continue
            self._ser = ser
            loop.call_soon_threadsafe(self._set_conn, True, f"已打开 {self.cfg.port}")
            try:
                while not self._stop.is_set():
                    line = ser.readline()
                    if not line:
                        continue
                    t_pc, t_wall = time.monotonic(), time.time()   # 尽早打接收时间戳
                    loop.call_soon_threadsafe(self._on_line, line, t_pc, t_wall)
            except Exception as e:
                loop.call_soon_threadsafe(self._set_conn, False, f"串口断开: {e}")
            finally:
                self._ser = None
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(0.5)

    def _on_line(self, line: bytes, t_pc: float, t_wall: float) -> None:
        text = line.decode("utf-8", "replace").strip()
        if not text:
            return
        self.sink.on_raw("receiver", text, t_pc, t_wall)
        if not text.startswith("{"):
            return    # 启动日志等非协议行：只进原始日志
        try:
            o = json.loads(text)
            t = o.get("t")
            if t == "imu":
                self.sink.on_imu(parse_imu_line(o, t_pc, t_wall))
            elif t == "hb":
                self.board["heartbeat"], self.board["last_hb_pc"] = o, t_pc
            elif t == "btn":
                self.sink.on_button(o, t_pc, t_wall)
        except Exception:
            self.board["parse_errors"] += 1

    def send_command(self, cmd: dict) -> bool:
        """向接收板发一行 JSON 指令（如 LED）。未连接时返回 False，不阻塞、不缓存旧指令。"""
        ser = self._ser
        if ser is None:
            return False
        try:
            with self._wlock:
                ser.write((json.dumps(cmd, separators=(",", ":")) + "\n").encode())
            return True
        except Exception:
            return False

    def board_status(self, now_pc: float) -> dict:
        b = dict(self.board)
        last = b.pop("last_hb_pc")
        b["heartbeat_age_s"] = None if last is None else round(now_pc - last, 2)
        return b
