"""配置加载：default.yaml + 可选 local.yaml 覆盖，pydantic 校验。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceCfg(_M):
    driver: str = "sim"
    port: Optional[str] = None
    baud: int = 921600
    stale_timeout_s: float = 1.0


class SourcesCfg(_M):
    wristband: SourceCfg = SourceCfg(stale_timeout_s=0.5)
    radar: SourceCfg = SourceCfg()
    required: list[Literal["wristband", "radar"]] = ["wristband", "radar"]


class ServoCfg(_M):
    driver: str = "sim"
    port: Optional[str] = None
    channel: Optional[int] = None
    pulse_min_us: int = 500
    pulse_max_us: int = 2500
    home_pulse_us: Optional[int] = None
    release_pulse_us: Optional[int] = None
    demo_pulse_us: Optional[int] = None
    move_time_ms: Optional[int] = None


class LedCfg(_M):
    driver: str = "sim"


class ActuatorsCfg(_M):
    servo: ServoCfg = ServoCfg()
    led: LedCfg = LedCfg()


class WristCfg(_M):
    window_s: float = 0.6
    impact_accel_ms2: float = 25.0
    freefall_accel_ms2: float = 4.0
    gyro_dps: float = 200.0


class ZoneCfg(_M):
    x: Optional[tuple[float, float]] = None
    y: Optional[tuple[float, float]] = None


class RadarRuleCfg(_M):
    window_s: float = 1.0
    height_drop_m: float = 0.5
    min_track_frames: int = 5
    zone: Optional[ZoneCfg] = None


class FusionCfg(_M):
    init_settle_s: float = 1.0
    suspect_timeout_s: float = 3.0
    coincidence_s: float = 1.0
    wrist: WristCfg = WristCfg()
    radar: RadarRuleCfg = RadarRuleCfg()


class ServerCfg(_M):
    operator_host: str = "127.0.0.1"
    operator_port: int = 8765
    mobile_host: str = "0.0.0.0"
    mobile_port: int = 8000
    status_push_hz: float = 5.0


class ApnsCfg(_M):
    enabled: bool = False
    use_sandbox: bool = True


class Config(_M):
    data_dir: str = "data"
    sources: SourcesCfg = SourcesCfg()
    actuators: ActuatorsCfg = ActuatorsCfg()
    fusion: FusionCfg = FusionCfg()
    server: ServerCfg = ServerCfg()
    apns: ApnsCfg = ApnsCfg()

    def version_hash(self) -> str:
        """配置内容指纹，写入日志，便于回放时确认用的是哪份配置。"""
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(config_dir: str | Path = "config", extra: Optional[dict] = None) -> Config:
    config_dir = Path(config_dir)
    data: dict = {}
    for name in ("default.yaml", "local.yaml"):
        p = config_dir / name
        if p.exists():
            data = _deep_merge(data, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    if extra:
        data = _deep_merge(data, extra)
    return Config.model_validate(data)
