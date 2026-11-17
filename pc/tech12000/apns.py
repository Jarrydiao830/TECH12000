"""APNs 可见推送（第二阶段）—— 接口占位，尚未实现发送。

第一阶段（App 前台 + WebSocket）不需要本模块。
实现时：HTTP/2 + ES256 JWT；密钥只从环境变量指向的本地 .p8 文件读取，
绝不写入仓库、App 或固件：
  TECH12000_APNS_KEY_PATH / TECH12000_APNS_KEY_ID /
  TECH12000_APNS_TEAM_ID  / TECH12000_APNS_BUNDLE_ID
通知用 apns-collapse-id = event_id 去重；不承诺即时送达。
"""
from __future__ import annotations

import logging
import os

from .config import ApnsCfg
from .models import FallEvent
from .store import Store

log = logging.getLogger(__name__)

ENV_KEYS = ("TECH12000_APNS_KEY_PATH", "TECH12000_APNS_KEY_ID",
            "TECH12000_APNS_TEAM_ID", "TECH12000_APNS_BUNDLE_ID")


class ApnsSender:
    def __init__(self, cfg: ApnsCfg, store: Store):
        self.cfg, self.store = cfg, store

    def status(self) -> dict:
        missing = [k for k in ENV_KEYS if not os.environ.get(k)]
        return {"enabled": self.cfg.enabled, "implemented": False,
                "credentials_present": not missing, "registered_tokens": len(self.store.apns_tokens())}

    async def notify(self, ev: FallEvent) -> None:
        if not self.cfg.enabled:
            return
        log.warning("APNs is enabled in config, but sending is not implemented yet (phase 2). Event %s was not pushed.", ev.event_id)
