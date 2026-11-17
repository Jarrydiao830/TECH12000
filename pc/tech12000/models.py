"""核心数据模型。单位与时间基准在此统一定义。

时间字段约定：
  t_pc    电脑接收时刻，time.monotonic()，秒。只用于本机内的间隔计算。
  t_wall  电脑接收时刻，UNIX 时间，秒。用于日志与对外展示。
  t_est   估计的"实际采样时刻"，换算到电脑 monotonic 时基（见 timebase.py）。
  设备自身时间戳只与同一设备、同一 session 内的其他时间戳比较。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class SystemState(str, Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    SUSPECTED_FALL = "suspected_fall"
    TRIGGERED = "triggered"
    FAULT = "fault"


class Mode(str, Enum):
    MONITOR = "monitor"  # 仅监测和记录
    DEMO = "demo"        # LED + 脱离实际释放机构的舵机演示
    ARMED = "armed"      # 人工明确启用后允许实际释放


class DeployStatus(str, Enum):
    NONE = "none"
    NOT_SENT_MONITOR = "not_sent_monitor_mode"
    DEMO_SENT = "demo_command_sent"
    COMMAND_SENT = "command_sent"
    CONTROLLER_ACKED = "controller_acked"   # 仅当控制器协议支持确认时出现
    SEND_FAILED = "send_failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"


# 没有气囊压力/展开到位反馈，实际展开结果永远是未知，直到人工检查。
DEPLOY_OUTCOME_UNKNOWN = "unknown_check_required"


@dataclass(slots=True)
class ImuSample:
    device_id: str
    session_id: int
    seq: int
    accel: tuple[float, float, float]     # m/s^2，传感器坐标系
    gyro: tuple[float, float, float]      # deg/s，传感器坐标系
    t_pc: float
    t_wall: float
    t_mcu_us: Optional[int] = None        # XIAO 收齐该帧IMU数据的本地时间
    t_imu_us: Optional[int] = None        # IMU 自带采样时间戳（模块不提供则为 None）
    t_board_us: Optional[int] = None      # 固定端接收板收到 ESP-NOW 包的本地时间
    flags: int = 0
    rssi: Optional[int] = None
    simulated: bool = False
    t_est: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RadarTarget:
    """一个跟踪目标。字段是否存在取决于雷达固件实际输出，缺失即 None。"""
    track_id: Optional[int] = None
    x: Optional[float] = None   # m
    y: Optional[float] = None   # m
    z: Optional[float] = None   # m，高度方向；坐标定义待SDK文档确认
    vx: Optional[float] = None
    vy: Optional[float] = None
    vz: Optional[float] = None


@dataclass(slots=True)
class RadarFrame:
    seq: int
    t_pc: float
    t_wall: float
    targets: list[RadarTarget] = field(default_factory=list)
    # 点云 (x_m, y_m, z_m, v_mps, snr_db)，雷达坐标系；固件支持且为笛卡尔坐标时才有
    points: Optional[list[tuple[float, float, float, float, float]]] = None
    t_device_us: Optional[int] = None
    device_frame: Optional[int] = None    # 雷达自带帧序号（RS6240 0xC3 frameIdx）
    cloud_kind: Optional[str] = None      # motion / presence
    # 人体关节 (name, x_m, y_m, z_m)。目前只有模拟源给出；真实雷达固件是否输出骨架尚未确认，没有就是 None
    joints: Optional[list[tuple[str, float, float, float]]] = None
    simulated: bool = False
    t_est: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class FallEvent:
    event_id: str
    t_wall: float                 # 判定发生的实际时间（补发时保持不变）
    mode: Mode                    # 判定时的执行模式
    simulated_input: bool         # 输入是否来自模拟/回放数据
    deploy_status: DeployStatus = DeployStatus.NONE
    deploy_outcome: str = DEPLOY_OUTCOME_UNKNOWN
    detail: dict = field(default_factory=dict)

    @property
    def is_test(self) -> bool:
        return self.mode is Mode.DEMO or self.simulated_input

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["deploy_status"] = self.deploy_status.value
        d["is_test"] = self.is_test
        d["message"] = event_message(self)
        return d


def event_message(ev: FallEvent) -> str:
    """通知文案：只陈述真实发生的事，不声称气囊已展开或保护成功。"""
    prefix = "[Simulated test] " if ev.is_test else ""
    s = ev.deploy_status
    if s in (DeployStatus.COMMAND_SENT, DeployStatus.CONTROLLER_ACKED):
        body = "Possible fall detected. Airbag release command sent. Actual inflation is unknown. Check on the person now."
    elif s is DeployStatus.DEMO_SENT:
        body = "Possible fall detected. Airbag demo command sent (no real release mechanism connected)."
    elif s is DeployStatus.SEND_FAILED:
        body = "Possible fall detected. Airbag command FAILED to send. Check on the person now."
    else:
        body = "Possible fall detected. Monitor-only mode, no deploy command sent. Check on the person now."
    return prefix + body
