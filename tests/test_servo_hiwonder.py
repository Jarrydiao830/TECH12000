"""Hiwonder 驱动：帧必须与《LSC 系列控制板通信协议 V1.1》中的示例逐字节一致。"""
import threading
import time

import pytest

from tech12000.actuators.servo_hiwonder import (
    CMD_ACTION_GROUP_RUN, FrameParser, HiwonderServo, build_get_voltage, build_servo_move)


def h(s: str) -> bytes:
    return bytes.fromhex(s.replace("0x", "").replace(",", " "))


# ---------------------------------------------------------------- 协议文档示例
def test_doc_example_single_servo():
    # 1 号舵机 1000ms 转到 2000
    assert build_servo_move([(1, 2000)], 1000) == h("55 55 08 03 01 E8 03 01 D0 07")


def test_doc_example_two_servos():
    # 2 号 -> 1200，9 号 -> 2300，800ms
    assert build_servo_move([(2, 1200), (9, 2300)], 800) == h("55 55 0B 03 02 20 03 02 B0 04 09 FC 08")


def test_doc_example_get_voltage():
    assert build_get_voltage() == h("55 55 02 0F")


def test_doc_example_voltage_reply_parsed():
    assert FrameParser().feed(h("55 55 04 0F 4C 1D")) == [(15, h("4C 1D"))]   # 7500 mV


# ---------------------------------------------------------------- 越界拒绝而不是限幅
@pytest.mark.parametrize("ch,pulse,t", [(16, 1500, 100), (-1, 1500, 100), (1, 499, 100),
                                        (1, 2501, 100), (1, 1500, -1), (1, 1500, 30001)])
def test_out_of_range_rejected(ch, pulse, t):
    with pytest.raises(ValueError):
        build_servo_move([(ch, pulse)], t)


def test_parser_resyncs_and_splits_chunks():
    p = FrameParser()
    stream = h("00 55 13 55 55 04 0F 4C 1D 55 55 05 06 08 01 00")
    out = []
    for b in stream:                       # 逐字节喂，模拟串口分包
        out += p.feed(bytes([b]))
    assert out == [(15, h("4C 1D")), (CMD_ACTION_GROUP_RUN, h("08 01 00"))]
    assert p.dropped == 3


def test_parser_rejects_unknown_length():
    # 电压应答长度不对 -> 不当成电压
    assert FrameParser().feed(h("55 55 05 0F 4C 1D 00")) == []


# ---------------------------------------------------------------- 驱动行为
class FakeSerial:
    def __init__(self, voltage_reply=True):
        self.written: list[bytes] = []
        self.voltage_reply = voltage_reply
        self._rx = bytearray()
        self._lock = threading.Lock()
        self.closed = False

    def write(self, b):
        self.written.append(bytes(b))
        if self.voltage_reply and bytes(b) == build_get_voltage():
            with self._lock:
                self._rx += h("55 55 04 0F 4C 1D")

    def flush(self):
        pass

    def read(self, n):
        time.sleep(0.01)
        with self._lock:
            out, self._rx[:] = bytes(self._rx[:n]), self._rx[n:]
        return out

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_not_ready_and_refuses_move_without_voltage_reply():
    clk = Clock()
    s = HiwonderServo("/dev/fake", clock=clk)
    s._ser = FakeSerial()
    assert not s.ready
    with pytest.raises(RuntimeError):
        s.move(1, 1500, 300)
    assert s._ser.written == []           # 未就绪时一个字节都不发


def test_ready_after_voltage_and_expires():
    clk = Clock()
    s = HiwonderServo("/dev/fake", clock=clk)
    s._ser = FakeSerial()
    s.handle_bytes(h("55 55 04 0F 4C 1D"))
    assert s.ready and s.voltage_mv == 7500
    assert s.move(1, 1900, 300) is None   # 无确认 -> None，界面显示"指令已发送"
    assert s._ser.written == [build_servo_move([(1, 1900)], 300)]
    clk.t += 3.5
    assert not s.ready


def test_move_out_of_range_sends_nothing():
    clk = Clock()
    s = HiwonderServo("/dev/fake", clock=clk)
    s._ser = FakeSerial()
    s.handle_bytes(h("55 55 04 0F 4C 1D"))
    with pytest.raises(ValueError):
        s.move(1, 2600, 300)
    assert s._ser.written == []


def test_unsolicited_action_group_recorded():
    s = HiwonderServo("/dev/fake", clock=Clock())
    s.handle_bytes(h("55 55 05 06 64 01 00"))     # 100 号动作组（板上 Run 键）开始运行
    assert s.last_unsolicited["group"] == 100


def test_background_thread_polls_voltage_and_never_moves_on_open():
    fake = FakeSerial()
    s = HiwonderServo("/dev/fake", serial_factory=lambda port: fake)
    s.open()
    try:
        deadline = time.monotonic() + 2
        while not s.ready and time.monotonic() < deadline:
            time.sleep(0.02)
        assert s.ready
        assert all(w == build_get_voltage() for w in fake.written)   # 只查询电压，没有位置指令
    finally:
        s.close()
    assert fake.closed and not s.ready


def test_background_thread_not_ready_when_controller_silent():
    fake = FakeSerial(voltage_reply=False)
    s = HiwonderServo("/dev/fake", serial_factory=lambda port: fake)
    s.open()
    try:
        time.sleep(0.2)
        assert not s.ready
        assert "waiting for voltage reply" in s.detail
    finally:
        s.close()


def test_no_port_configured():
    s = HiwonderServo(None)
    s.open()
    try:
        time.sleep(0.05)
        assert not s.ready and "not configured" in s.detail
    finally:
        s.close()
