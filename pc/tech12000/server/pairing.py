"""手机配对令牌：首次运行生成并保存在数据目录，App 每次请求都要带。"""
from __future__ import annotations

import hmac
import os
import secrets
import socket
from pathlib import Path


def load_or_create_token(data_dir: str | Path) -> str:
    p = Path(data_dir) / "pairing_token"
    if p.exists():
        tok = p.read_text().strip()
        if tok:
            return tok
    p.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(24)
    p.write_text(tok)
    os.chmod(p, 0o600)
    return tok


def rotate_token(data_dir: str | Path) -> str:
    p = Path(data_dir) / "pairing_token"
    if p.exists():
        p.unlink()
    return load_or_create_token(data_dir)


def token_ok(expected: str, authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected.encode(), authorization[7:].strip().encode())


def lan_ip() -> str:
    """本机在局域网中的地址（不实际发包）。取不到时返回 127.0.0.1。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
