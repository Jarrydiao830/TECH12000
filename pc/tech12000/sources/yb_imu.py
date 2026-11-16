"""亚博 IMU 串口协议（与 firmware/wristband/src/yb_imu_protocol.h 同一套规则），供电脑直连模块排查用。

依据 imu/通信协议/通信协议.xlsx：帧 = 7E 23 LEN FUNC DATA.. SUM，LEN 为整帧长度，
SUM = 帧头到校验前一字节之和的低 8 位；FUNC 0x04 为 int16 小端的 accel/gyro/mag，
accel 比例 16/32767 g，gyro 比例 2000/32767 °/s。
"""
from __future__ import annotations

import struct
from typing import Optional

HEAD = b"\x7e\x23"
FUNC_RAW, FUNC_SET_RATE = 0x04, 0x60
RAW_LEN, MAX_LEN = 0x17, 40
G = 9.80665


def checksum(b: bytes) -> int:
    return sum(b) & 0xFF


def build_set_rate(hz: int) -> bytes:
    if not 10 <= hz <= 100:
        raise ValueError("输出频率只能 10~100 Hz")
    f = bytes((0x7E, 0x23, 7, FUNC_SET_RATE, hz, 0x5F))
    return f + bytes((checksum(f),))


class YbImuParser:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.stats = {"raw": 0, "other": 0, "checksum_err": 0, "skipped": 0}

    def feed(self, data: bytes) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
        """返回 [(accel m/s², gyro °/s)]。"""
        self.buf += data
        out = []
        b = self.buf
        while True:
            i = b.find(HEAD)
            if i < 0:
                keep = 1 if b.endswith(b"\x7e") else 0
                self.stats["skipped"] += len(b) - keep
                del b[: len(b) - keep]
                break
            if i:
                self.stats["skipped"] += i
                del b[:i]
            if len(b) < 3:
                break
            n = b[2]
            if not 5 <= n <= MAX_LEN:
                self.stats["skipped"] += 1
                del b[:1]
                continue
            if len(b) < n:
                break
            fr = bytes(b[:n])
            if checksum(fr[:-1]) != fr[-1]:
                self.stats["checksum_err"] += 1
                del b[:1]
                continue
            del b[:n]
            if fr[3] == FUNC_RAW and n == RAW_LEN:
                v = struct.unpack_from("<9h", fr, 4)
                self.stats["raw"] += 1
                out.append((tuple(x * 16 / 32767 * G for x in v[0:3]), tuple(x * 2000 / 32767 for x in v[3:6])))
            else:
                self.stats["other"] += 1
        return out
