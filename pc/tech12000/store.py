"""持久化：事件、执行台账、APNs token。

执行台账是"同一事件只执行一次"的依据：发舵机指令【之前】先落盘占位，
event_id 为主键。程序重启、USB重连、重复消息、网络重试都无法让同一
event_id 第二次占位成功。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .models import DeployStatus, FallEvent, Mode


class Store:
    def __init__(self, path: str | Path):
        self._lock = threading.Lock()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS events(
                event_id TEXT PRIMARY KEY, t_wall REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS actuations(
                event_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                t_claim REAL NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS apns_tokens(
                token TEXT PRIMARY KEY, t_wall REAL NOT NULL);
            """
        )
        self._db.commit()

    # ---- events ----
    def save_event(self, ev: FallEvent) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO events(event_id,t_wall,body) VALUES(?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET body=excluded.body",
                (ev.event_id, ev.t_wall, json.dumps(ev.to_dict(), ensure_ascii=False)),
            )
            self._db.commit()

    def list_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT body FROM events ORDER BY t_wall DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get_event(self, event_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM events WHERE event_id=?", (event_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    # ---- actuation ledger ----
    def claim_actuation(self, event_id: str, kind: str) -> bool:
        """原子占位。返回 False 表示该事件已被处理过（不论当时成功与否），绝不重发。"""
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO actuations(event_id,kind,t_claim,status) VALUES(?,?,?,?)",
                    (event_id, kind, time.time(), "claimed"),
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def finish_actuation(self, event_id: str, status: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE actuations SET status=? WHERE event_id=?", (status, event_id)
            )
            self._db.commit()

    def get_actuation(self, event_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                "SELECT kind,t_claim,status FROM actuations WHERE event_id=?", (event_id,)
            ).fetchone()
        return {"kind": row[0], "t_claim": row[1], "status": row[2]} if row else None

    # ---- APNs tokens ----
    def add_apns_token(self, token: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO apns_tokens(token,t_wall) VALUES(?,?)",
                (token, time.time()),
            )
            self._db.commit()

    def apns_tokens(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT token FROM apns_tokens")]

    def close(self) -> None:
        with self._lock:
            self._db.close()
