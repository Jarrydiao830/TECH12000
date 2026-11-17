"""正和微芯 RS6x/7x HIF 协议：帧解析、0xC3 点云分片重组、点解码。纯函数，无 I/O。

依据（厂家 SDK RS6x_7x_mmWave_sdk_V2.1.2，本地副本见 docs/vendor/rs6240/）：
  - 《RS6x_7x_HIF_参考手册_V1.2》3.1 帧格式、3.1.3.2.3 点云目标 (0xC3)
  - HostSample_V1.0.1 主机驱动源码：
      protocol/hif/hif_type.h        —— 魔数、标志位
      protocol/hif/host_hif_tl.c     —— Check8 / Check32 校验、帧头搜索
      cmd_api/rs6x_7x/host_mmw_api.h —— FrameData_C3_t / Frame_Point_t
      cmd_api/rs6x_7x/host_mmw_report_api.c —— 0xC1/0xC3 分片重组（偏移单位 DWORD）
      ESP32S3_Project/main/viz_server.c —— 点字段按 int16 读取、单位换算

线上格式（UART，无对齐填充；SPI 才有填充字节）：
  [0xA5][Check8][MsgHdr 4B LE][Payload N][Check32 4B LE，仅当 flag.bit2]
  Check8 ：6 个头字节按 uint8 累加 == 0xFF
  Check32：Check32 + Σ(payload 按小端 DWORD，尾部高位补零) + MsgHdr(uint32) == 0xFFFFFFFF
  MsgHdr 位域：type[1:0] flag[7:2] msg_id[15:8] length[27:16] seq[30:28] frag[31]
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

MAGIC = 0xA5
HEAD_LEN = 6
CHECK32_LEN = 4

FLAG_REQ = 1 << 0
FLAG_CHECK32 = 1 << 2
FLAG_MORE = 1 << 3
FLAG_EXT = 1 << 4

TYPE_HOST_TO_DEV, TYPE_DEV_TO_HOST, TYPE_DEBUG = 1, 2, 3

MSG_POINT_CLOUD = 0xC3
MSG_HEARTBEAT = 0xFE
MSG_STARTUP = 0xFF

C3_HDR = struct.Struct("<III")        # frameIdx, frameLen(DWORD), dataOffset(DWORD)
C3_INFO = struct.Struct("<BBH")       # type, flag, total_length
POINT = struct.Struct("<hhhhhH")      # x/range, y/azimuth, z/elevation, velocity, snr, reserved
POINT_TYPE = 4                        # 手册：点云数据 Type 固定为 4


# ---------------------------------------------------------------- 帧层
@dataclass(slots=True)
class HifFrame:
    type: int
    flag: int
    msg_id: int
    seq: int
    frag: bool
    payload: bytes
    check32_ok: Optional[bool]        # None = 帧未携带 Check32


def check8_ok(head6: bytes) -> bool:
    return sum(head6) & 0xFF == 0xFF


def sum32(data: bytes) -> int:
    pad = (-len(data)) % 4
    d = data + b"\x00" * pad
    return sum(struct.unpack(f"<{len(d) // 4}I", d)) & 0xFFFFFFFF


def unpack_msghdr(v: int) -> tuple[int, int, int, int, int, bool]:
    return (v & 0x3, (v >> 2) & 0x3F, (v >> 8) & 0xFF, (v >> 16) & 0xFFF, (v >> 28) & 0x7, bool(v >> 31))


def pack_msghdr(type_: int, flag: int, msg_id: int, length: int, seq: int = 0, frag: bool = False) -> int:
    return (type_ & 0x3) | ((flag & 0x3F) << 2) | ((msg_id & 0xFF) << 8) | ((length & 0xFFF) << 16) \
        | ((seq & 0x7) << 28) | (int(frag) << 31)


def build_frame(msg_id: int, payload: bytes, *, type_: int = TYPE_DEV_TO_HOST, flag: int = FLAG_CHECK32,
                seq: int = 0, frag: bool = False) -> bytes:
    """按上面的线上格式组帧。用于测试和主机→设备命令。"""
    if len(payload) > 0xFFF:
        raise ValueError("payload exceeds 4095 bytes")
    hdr = pack_msghdr(type_, flag, msg_id, len(payload), seq, frag)
    hdr_b = struct.pack("<I", hdr)
    c8 = (~(MAGIC + sum(hdr_b))) & 0xFF
    out = bytes((MAGIC, c8)) + hdr_b + payload
    if flag & FLAG_CHECK32:
        out += struct.pack("<I", (~(sum32(payload) + hdr)) & 0xFFFFFFFF)
    return out


class HifStreamParser:
    """从串口字节流中切出 HIF 帧。帧头靠 0xA5 + Check8 定位，失败则后移一个字节继续找。"""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.stats = {"frames": 0, "skipped_bytes": 0, "check32_fail": 0}

    def feed(self, data: bytes) -> list[HifFrame]:
        self.buf += data
        out: list[HifFrame] = []
        b = self.buf
        while True:
            i = b.find(MAGIC)
            if i < 0:
                self.stats["skipped_bytes"] += len(b)
                b.clear()
                break
            if i:
                self.stats["skipped_bytes"] += i
                del b[:i]
            if len(b) < HEAD_LEN:
                break
            if not check8_ok(bytes(b[:HEAD_LEN])):
                self.stats["skipped_bytes"] += 1
                del b[:1]
                continue
            hdr = struct.unpack_from("<I", b, 2)[0]
            type_, flag, msg_id, length, seq, frag = unpack_msghdr(hdr)
            tail = CHECK32_LEN if flag & FLAG_CHECK32 else 0
            total = HEAD_LEN + length + tail
            if len(b) < total:
                break
            payload = bytes(b[HEAD_LEN:HEAD_LEN + length])
            ok: Optional[bool] = None
            if tail:
                c32 = struct.unpack_from("<I", b, HEAD_LEN + length)[0]
                ok = (c32 + sum32(payload) + hdr) & 0xFFFFFFFF == 0xFFFFFFFF
                if not ok:
                    self.stats["check32_fail"] += 1
                    # 头校验通过但数据校验失败：丢弃整帧，不当作有效数据
                    del b[:total]
                    continue
            del b[:total]
            self.stats["frames"] += 1
            out.append(HifFrame(type_, flag, msg_id, seq, frag, payload, ok))
        return out


# ---------------------------------------------------------------- 0xC3 点云
@dataclass(slots=True)
class PointCloud:
    frame_idx: int
    cartesian: bool               # flag.bit0
    kind: str                     # "motion" | "presence" | "other"
    points: list[tuple[float, float, float, float, float]] = field(default_factory=list)
    # 笛卡尔：(x_m, y_m, z_m, v_mps, snr_db)；极坐标：(range_m, azimuth_deg, elevation_deg, v_mps, snr_db)


class C3Reassembler:
    """按 frameIdx / dataOffset 把 0xC3 分片拼成整帧。分片缺失或乱序则整帧丢弃（不重传）。"""

    def __init__(self) -> None:
        self._idx: Optional[int] = None
        self._need = 0
        self._buf = bytearray()
        self.stats = {"frames": 0, "dropped": 0, "bad": 0}

    def feed(self, payload: bytes) -> Optional[PointCloud]:
        if len(payload) < C3_HDR.size:
            self.stats["bad"] += 1
            return None
        idx, flen, off = C3_HDR.unpack_from(payload)
        data = payload[C3_HDR.size:]
        need, off_b = flen * 4, off * 4
        if self._idx != idx:
            if self._idx is not None and len(self._buf) < self._need:
                self.stats["dropped"] += 1
            self._idx, self._need, self._buf = idx, need, bytearray()
            if off_b != 0:                  # 新帧却不是从头开始：前面的分片丢了
                self._idx = None
                self.stats["dropped"] += 1
                return None
        if self._idx is None or off_b != len(self._buf):
            self.stats["dropped"] += 1
            self._idx = None
            return None
        self._buf += data
        if len(self._buf) < self._need:
            return None
        whole, self._idx = bytes(self._buf[: self._need]), None
        pc = decode_c3(idx, whole)
        if pc is None:
            self.stats["bad"] += 1
        else:
            self.stats["frames"] += 1
        return pc


def decode_c3(frame_idx: int, data: bytes) -> Optional[PointCloud]:
    """data = 重组后的点云数据（不含 12 字节分片头）：type, flag, total_length, 点[]。"""
    if len(data) < C3_INFO.size:
        return None
    type_, flag, _total = C3_INFO.unpack_from(data)
    if type_ != POINT_TYPE:
        return None
    n = (len(data) - C3_INFO.size) // POINT.size     # 与厂家 HOST_MMW_GET_C3_DATA_LENGTH 一致
    cart = bool(flag & 0x1)
    k = (flag >> 1) & 0x3
    kind = "motion" if k == 0 else "presence" if k == 1 else "other"
    pts = []
    for i in range(n):
        a, b, c, v, snr, _ = POINT.unpack_from(data, C3_INFO.size + i * POINT.size)
        # 笛卡尔 cm -> m；极坐标 range cm -> m、角度 0.01° -> °。两者都是 /100
        pts.append((a / 100, b / 100, c / 100, v / 100, snr / 100))
    return PointCloud(frame_idx, cart, kind, pts)


def build_c3_payloads(frame_idx: int, flag: int, points: list[tuple[int, int, int, int, int]],
                      max_chunk: int = 4000) -> list[bytes]:
    """测试用：把原始整数点（cm、cm/s、0.01dB）打包成若干 0xC3 payload。"""
    body = C3_INFO.pack(POINT_TYPE, flag, 0) + b"".join(POINT.pack(*p, 0) for p in points)
    body += b"\x00" * ((-len(body)) % 4)
    body = C3_INFO.pack(POINT_TYPE, flag, len(body)) + body[C3_INFO.size:]
    chunk = max_chunk - max_chunk % 4
    out = []
    for off in range(0, len(body), chunk):
        out.append(C3_HDR.pack(frame_idx, len(body) // 4, off // 4) + body[off:off + chunk])
    return out
