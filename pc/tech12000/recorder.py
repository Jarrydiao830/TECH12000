"""会话日志：所有输入、状态变化、指令与确认都追加写入 JSONL，供离线回放。

写盘在独立线程，采集/判断线程只做入队，磁盘慢不会阻塞本地处理。
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from . import __version__


class Recorder:
    def __init__(self, data_dir: str | Path, config_dump: dict, config_version: str):
        name = time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(data_dir) / "sessions" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(
            json.dumps(
                {
                    "started_wall": time.time(),
                    "software_version": __version__,
                    "config_version": config_version,
                    "config": config_dump,
                    "units": {"accel": "m/s^2", "gyro": "deg/s", "radar_xyz": "m"},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._q: queue.Queue = queue.Queue(maxsize=50000)
        self.dropped = 0
        self._f = open(self.dir / "stream.jsonl", "a", encoding="utf-8")
        self._t = threading.Thread(target=self._run, name="recorder", daemon=True)
        self._t.start()

    def write(self, kind: str, payload: dict) -> None:
        try:
            self._q.put_nowait((kind, payload))
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        last_flush = time.monotonic()
        while True:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                item = False
            if item is None:
                break
            if item:
                kind, payload = item
                self._f.write(json.dumps({"k": kind, **payload}, ensure_ascii=False) + "\n")
                # 状态/事件/指令立即落盘；高频数据按时间批量落盘
                if kind not in ("imu", "radar", "raw"):
                    self._f.flush()
            if time.monotonic() - last_flush > 0.5:
                self._f.flush()
                last_flush = time.monotonic()
        self._f.flush()
        self._f.close()

    def close(self) -> None:
        self._q.put(None)
        self._t.join(timeout=3)


class NullRecorder:
    dir: Optional[Path] = None
    dropped = 0

    def write(self, kind: str, payload: dict) -> None:
        pass

    def close(self) -> None:
        pass
