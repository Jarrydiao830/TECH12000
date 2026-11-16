"""幻尔 Hiwonder 16 路舵机控制器（板上丝印 LSC-16-V1.3）驱动。

依据（厂家资料，本地副本见 docs/vendor/hiwonder/）：
  - 《LSC 系列控制板通信协议 V1.1》：串口 9600，帧 = 0x55 0x55 Length Cmd Prm1..PrmN，
    Length = N + 2，无校验字节。
  - 《16路舵机控制器使用说明》：USB 口经 CH341 系列 USB 转串口芯片连接电脑；
    位置 500–2500 对应 0–180°，1500 为中位；供电 5–8.4 V。
  - 厂家树莓派示例 ServoControl.py：参数小端；时间限幅 0–30000 ms。

与本项目安全约束相关的结论：
  - CMD_SERVO_MOVE (3) 没有串口应答（只有板上 LED2 闪一下），所以 supports_ack = False，
    界面只能显示"指令已发送"。
  - CMD_GET_BATTERY_VOLTAGE (15) 会立即返回电压。本驱动每秒查询一次，作为"控制器在线"的依据；
    它只说明控制器在线，不代表任何一条移动指令被执行。
  - 打开串口时不发送任何位置指令。手册写明"舵机上电后不会直接回到中位"，
    上电瞬间各通道输出什么手册没有说明，需实物观察。
  - 不使用动作组指令：动作组内容存在控制器里，电脑端看不到，可能与配置的释放位置不一致。

仍待实物确认：
  - macOS 能否直接枚举出 /dev/cu.* 设备（厂家只给了 Windows 驱动）。
  - 通道 0 是否可用：丝印编号 0–15，但厂家示例把 ID 限制在 1–254（0 会被改成 254）。
  - 控制器电源通路的电流能力（手册未给出），与 X70S 堵转电流是否匹配。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable, Optional

from .base import ServoDriver

log = logging.getLogger(__name__)

BAUD = 9600
HEADER = b"\x55\x55"

CMD_SERVO_MOVE = 3
CMD_ACTION_GROUP_RUN = 6
CMD_ACTION_GROUP_STOP = 7
CMD_ACTION_GROUP_COMPLETE = 8
CMD_ACTION_GROUP_SPEED = 11
CMD_GET_BATTERY_VOLTAGE = 15

CHANNEL_MIN, CHANNEL_MAX = 0, 15          # 板上丝印
PULSE_MIN, PULSE_MAX = 500, 2500          # 使用说明 1.4.2
TIME_MIN_MS, TIME_MAX_MS = 0, 30000       # 厂家示例限幅

VOLTAGE_POLL_S = 1.0
ONLINE_TIMEOUT_S = 3.0                    # 超过这么久没收到电压应答 -> 视为未就绪


# ---------------------------------------------------------------- 纯协议函数（无 I/O，便于测试）
def _frame(cmd: int, params: bytes = b"") -> bytes:
    length = len(params) + 2
    if length > 0xFF:
        raise ValueError("帧过长")
    return HEADER + bytes((length, cmd)) + params


def build_servo_move(targets: Iterable[tuple[int, int]], time_ms: int) -> bytes:
    """CMD_SERVO_MOVE。targets = [(通道, 位置)]。超范围直接报错，不做限幅。"""
    targets = list(targets)
    if not targets:
        raise ValueError("至少需要一个舵机")
    if not TIME_MIN_MS <= time_ms <= TIME_MAX_MS:
        raise ValueError(f"time_ms={time_ms} 超出 [{TIME_MIN_MS},{TIME_MAX_MS}]")
    params = bytearray((len(targets),)) + int(time_ms).to_bytes(2, "little")
    for ch, pulse in targets:
        if not CHANNEL_MIN <= ch <= CHANNEL_MAX:
            raise ValueError(f"通道 {ch} 超出 [{CHANNEL_MIN},{CHANNEL_MAX}]")
        if not PULSE_MIN <= pulse <= PULSE_MAX:
            raise ValueError(f"位置 {pulse} 超出 [{PULSE_MIN},{PULSE_MAX}]")
        params += bytes((ch,)) + int(pulse).to_bytes(2, "little")
    return _frame(CMD_SERVO_MOVE, bytes(params))


def build_get_voltage() -> bytes:
    return _frame(CMD_GET_BATTERY_VOLTAGE)


class FrameParser:
    """把串口字节流切成 (cmd, params)。协议没有校验字节，只能靠帧头 + 长度 + 已知指令做合理性检查。"""

    # 控制器会主动发送的指令及其参数长度（协议第二部分 + 电压应答）
    EXPECTED_PARAMS = {
        CMD_GET_BATTERY_VOLTAGE: 2,
        CMD_ACTION_GROUP_RUN: 3,
        CMD_ACTION_GROUP_STOP: 0,
        CMD_ACTION_GROUP_COMPLETE: 3,
    }

    def __init__(self) -> None:
        self.buf = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self.buf += data
        out = []
        while True:
            i = self.buf.find(HEADER)
            if i < 0:
                keep = 1 if self.buf.endswith(b"\x55") else 0
                self.dropped += len(self.buf) - keep
                del self.buf[: len(self.buf) - keep]
                break
            if i:
                self.dropped += i
                del self.buf[:i]
            if len(self.buf) < 4:
                break
            length, cmd = self.buf[2], self.buf[3]
            n = self.EXPECTED_PARAMS.get(cmd)
            if n is None or length != n + 2:
                self.dropped += 1
                del self.buf[:1]          # 不是合法帧：丢一个字节重新找帧头
                continue
            if len(self.buf) < 2 + length:
                break
            out.append((cmd, bytes(self.buf[4 : 2 + length])))
            del self.buf[: 2 + length]
        return out


# ---------------------------------------------------------------- 驱动
class HiwonderServo(ServoDriver):
    name = "hiwonder"
    supports_ack = False     # CMD_SERVO_MOVE 无串口应答

    def __init__(self, port: Optional[str], *,
                 serial_factory: Optional[Callable[[str], object]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.port = port
        self._serial_factory = serial_factory or self._open_serial
        self._clock = clock
        self._ser = None
        self._wlock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._parser = FrameParser()
        self._conn_detail = "未启动"
        self.voltage_mv: Optional[int] = None
        self.last_voltage_t: Optional[float] = None
        self.last_unsolicited: Optional[dict] = None
        self.moves_sent = 0

    @staticmethod
    def _open_serial(port: str):
        import serial  # pyserial
        return serial.Serial(port, BAUD, timeout=0.2, write_timeout=0.5)

    # ---- 生命周期
    def open(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hiwonder-serial", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._drop_serial()

    def _drop_serial(self) -> None:
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.port:
                self._conn_detail = "未配置 actuators.servo.port"
                self._stop.wait(2)
                continue
            try:
                ser = self._serial_factory(self.port)
            except Exception as e:
                self._conn_detail = f"打不开串口: {e}"
                self._stop.wait(1)
                continue
            self._ser = ser
            self._parser = FrameParser()
            self._conn_detail = f"已打开 {self.port}，等待电压应答"
            log.info("Hiwonder 串口已打开 %s（不发送任何位置指令）", self.port)
            next_poll = 0.0
            try:
                while not self._stop.is_set():
                    now = self._clock()
                    if now >= next_poll:
                        self._write(build_get_voltage())
                        next_poll = now + VOLTAGE_POLL_S
                    data = ser.read(64)
                    if data:
                        self.handle_bytes(data)
            except Exception as e:
                self._conn_detail = f"串口断开: {e}"
                log.warning("Hiwonder 串口断开: %s", e)
            finally:
                self._drop_serial()
                self.last_voltage_t = None
            self._stop.wait(0.5)

    # ---- 收发
    def _write(self, frame: bytes) -> None:
        ser = self._ser
        if ser is None:
            raise RuntimeError("舵机控制器串口未连接")
        with self._wlock:
            ser.write(frame)
            ser.flush()          # 等字节真正发出，再算"已发送"

    def handle_bytes(self, data: bytes) -> None:
        for cmd, p in self._parser.feed(data):
            if cmd == CMD_GET_BATTERY_VOLTAGE:
                self.voltage_mv = int.from_bytes(p, "little")
                self.last_voltage_t = self._clock()
            else:
                # 动作组开始/停止/结束：本项目不使用动作组，出现即说明有人按了板上 Run 键或用了别的控制方式
                info = {"cmd": cmd, "params": p.hex(), "t": self._clock()}
                if cmd in (CMD_ACTION_GROUP_RUN, CMD_ACTION_GROUP_COMPLETE):
                    info["group"] = p[0]
                    info["times"] = int.from_bytes(p[1:3], "little")
                self.last_unsolicited = info
                log.warning("控制器主动上报（动作组）: %s", info)

    # ---- ServoDriver 接口
    @property
    def online(self) -> bool:
        t = self.last_voltage_t
        return self._ser is not None and t is not None and self._clock() - t <= ONLINE_TIMEOUT_S

    @property
    def ready(self) -> bool:
        return self.online

    @property
    def detail(self) -> str:
        if self.online:
            return f"在线（电压应答 {self.voltage_mv} mV）；移动指令无应答，只能确认已发送"
        if self._ser is not None and self.last_voltage_t is not None:
            return f"{ONLINE_TIMEOUT_S:.0f} 秒内没有电压应答（控制器开关/供电？）"
        return self._conn_detail

    def move(self, channel: int, pulse_us: int, time_ms: int) -> Optional[bool]:
        frame = build_servo_move([(channel, pulse_us)], time_ms)   # 先校验，超范围直接抛
        if not self.online:
            raise RuntimeError(f"舵机控制器未就绪：{self.detail}")
        self._write(frame)
        self.moves_sent += 1
        log.info("[Hiwonder] ch=%s pulse=%s time=%sms 已发送 %s", channel, pulse_us, time_ms, frame.hex(" "))
        return None          # 协议无确认

    def status(self) -> dict:
        s = super().status()
        age = None if self.last_voltage_t is None else round(self._clock() - self.last_voltage_t, 2)
        s.update(port=self.port, voltage_mv=self.voltage_mv, voltage_age_s=age,
                 moves_sent=self.moves_sent, parser_dropped=self._parser.dropped,
                 last_unsolicited=self.last_unsolicited)
        return s
