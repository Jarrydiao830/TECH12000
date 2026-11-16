"""RS6240 HIF 解析：帧格式与校验按厂家主机驱动源码（host_hif_tl.c / host_mmw_api.h）实现。

注意：这里的测试帧是按协议自行组帧的，不是真机抓包；真机验证见 `tech12000 radar-probe`。
"""
import struct

from tech12000.config import Config
from tech12000.fusion.features import RadarFeatures
from tech12000.models import RadarFrame
from tech12000.sources.radar_rs6240 import Rs6240Decoder
from tech12000.sources.rs6240_hif import (
    FLAG_CHECK32, MAGIC, C3Reassembler, HifStreamParser, build_c3_payloads, build_frame, check8_ok, sum32,
    unpack_msghdr)


def test_poll_template_header_matches_vendor():
    # 厂家 host_hif_tl.c: poll_template = {0xA5,0x0,0x15,0xC,...}，0x15 = type1 | flag(Req|Check32)<<2
    f = build_frame(0x0C, b"\x01\x00\x03\x00", type_=1, flag=0x05)
    assert f[0] == MAGIC and f[2] == 0x15 and f[3] == 0x0C
    assert check8_ok(f[:6])


def test_frame_roundtrip_and_check32():
    f = build_frame(0xC3, bytes(range(13)))          # 13 字节：测尾部补零
    hdr = struct.unpack_from("<I", f, 2)[0]
    c32 = struct.unpack_from("<I", f, 6 + 13)[0]
    assert (c32 + sum32(bytes(range(13))) + hdr) & 0xFFFFFFFF == 0xFFFFFFFF
    assert unpack_msghdr(hdr)[2:4] == (0xC3, 13)
    out = HifStreamParser().feed(f)
    assert len(out) == 1 and out[0].payload == bytes(range(13)) and out[0].check32_ok


def test_parser_resync_split_and_reject_bad_check32():
    good = build_frame(0xFE, b"\x01\x02\x03\x04")
    bad = bytearray(build_frame(0xC3, b"\x00" * 8))
    bad[-1] ^= 0xFF                                    # 破坏 Check32
    stream = b"\x00\xff\xa5\x13" + bytes(bad) + good
    p = HifStreamParser()
    frames = []
    for b in stream:                                   # 逐字节喂，模拟串口分包
        frames += p.feed(bytes([b]))
    assert [f.msg_id for f in frames] == [0xFE]
    assert p.stats["check32_fail"] == 1


def test_frame_without_check32():
    f = build_frame(0xFF, b"\x07", flag=0)
    out = HifStreamParser().feed(f)
    assert out[0].check32_ok is None and out[0].payload == b"\x07"


PTS = [(10, 150, 120, -30, 1500), (-20, 160, 90, -45, 1200), (0, 155, 60, -80, 900)]   # cm, cm/s, 0.01dB


def test_c3_single_piece_decodes_signed_units():
    (payload,) = build_c3_payloads(7, flag=0x01, points=PTS)
    pc = C3Reassembler().feed(payload)
    assert pc.frame_idx == 7 and pc.cartesian and pc.kind == "motion"
    assert pc.points[1] == (-0.2, 1.6, 0.9, -0.45, 12.0)


def test_c3_fragmented_reassembly_and_gap_drop():
    pts = [(i, 100 + i, 50 + i, -i, 1000) for i in range(40)]
    pieces = build_c3_payloads(9, flag=0x01 | 0x02, points=pts, max_chunk=100)
    assert len(pieces) > 3
    r = C3Reassembler()
    res = [r.feed(p) for p in pieces]
    assert res[:-1] == [None] * (len(pieces) - 1)
    assert len(res[-1].points) == 40 and res[-1].kind == "presence"

    r2 = C3Reassembler()
    for p in pieces[:1] + pieces[2:]:                   # 丢一片 -> 整帧丢弃，不输出半帧
        assert r2.feed(p) is None
    assert r2.stats["dropped"] >= 1


def test_decoder_end_to_end_over_bytes():
    stream = b"".join(build_frame(0xC3, p) for p in build_c3_payloads(3, 0x01, PTS))
    stream += build_frame(0xFE, b"")
    d = Rs6240Decoder()
    clouds = d.feed(stream)
    assert len(clouds) == 1 and d.counts["heartbeat"] == 1


# ---------------------------------------------------------------- 点云 -> 高度
def _feat(**pts_cfg):
    cfg = Config().fusion.radar
    for k, v in pts_cfg.items():
        setattr(cfg.points, k, v)
    return RadarFeatures(cfg)


def test_points_without_axis_configured_give_no_height():
    f = _feat()
    f.update(RadarFrame(seq=1, t_pc=0.0, t_wall=0.0, points=[(0, 1, 1, 0, 10)] * 5))
    assert f.height is None and "height_axis" in f.points_unusable


def test_points_height_from_axis_and_offset():
    f = _feat(height_axis="z", height_sign=-1, height_offset_m=2.0, min_points=3, percentile=1.0)
    pts = [(0.0, 1.5, z, 0.0, 10.0) for z in (0.8, 1.0, 1.2)]   # 雷达在 2 m 高处、z 朝下
    f.update(RadarFrame(seq=1, t_pc=0.0, t_wall=0.0, points=pts))
    assert abs(f.height - 1.2) < 1e-9
    f.update(RadarFrame(seq=2, t_pc=0.1, t_wall=0.1, points=pts[:2]))   # 点数不够 -> 无高度
    assert f.height is None


# ---------------------------------------------------------------- 亚博 IMU（电脑端排查用解析器）
def test_yb_imu_parser_matches_doc_examples():
    from tech12000.sources.yb_imu import YbImuParser, build_set_rate, checksum
    assert checksum(bytes.fromhex("7E 23 07 80 01 00")) == 0x29          # 协议表：请求固件版本
    assert build_set_rate(100) == bytes.fromhex("7E 23 07 60 64 5F") + bytes((checksum(bytes.fromhex("7E 23 07 60 64 5F")),))
    body = bytes.fromhex("7E 23 17 04") + struct.pack("<9h", 0, 0, 2048, 0, 0, 32767, 0, 0, 0)
    fr = body + bytes((checksum(body),))
    p = YbImuParser()
    out = p.feed(b"\x01\x7e" + fr[:10]) + p.feed(fr[10:])
    assert len(out) == 1
    (a, g), = out
    assert abs(a[2] - 9.80665) < 0.01 and abs(g[2] - 2000) < 1e-6
