# -*- coding: utf-8 -*-
"""会话与任务状态的落盘层 —— 让容器重启后不至于把用户的活儿全丢。

**问题**：`server.SESSIONS`（多轮追问上下文）和 `oneshot.JOBS`（一次性生成
任务）原来都是裸 dict。桌面版没问题——用户自己看着那个黑窗口，一关就没了是他
自己的选择。但容器会被 `docker compose up -d --build`、被 OOM Killer、被
滚动重启反复终止，进程一换内存就空了。用户看到的是「我刚才跑的任务不见了」。

**为什么不做成数据库**：这里的写入频率低（一次任务几条 JSON）、并发只有一个
（gunicorn 单 worker，见 Dockerfile 注释），SQLite 反而引入锁与迁移的复杂度。
用「一个 job 一个目录 + 一个 `_state.json`」最直白，出问题用 cat 就能看。

**为什么不追求强一致**：写到一半被杀，最坏是那条状态文件缺失——启动时跳过它，
任务列表少一条。这比「整个 store 损坏、所有任务都读不出来」好得多。

存储布局（在 `paths.data_root()` 下）：

    _oneshot/<job_id>/_state.json    任务状态（阶段、进度、产物清单）
    _sessions/<sid>.json             追问会话
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()

# 会话最多留多少条、留多久。不清理的话，长期运行的实例会把磁盘写满。
MAX_SESSIONS = 500
SESSION_MAX_AGE = 7 * 24 * 3600


def _sessions_dir() -> Path:
    import paths

    d = paths.data_root() / "_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(p: Path, text: str) -> None:
    """先写临时文件再 rename —— 进程被杀不会留下半截 JSON。

    同目录内 rename 在 POSIX 上是原子的；跨文件系统才不保险，所以临时文件
    必须和目标文件同目录（不能用系统 temp）。
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------- 会话

def save_session(sid: str, data: dict) -> None:
    """保存一个追问会话。失败静默——会话丢失不该让请求 500。"""
    try:
        data = dict(data)
        data["_saved_at"] = time.time()
        _atomic_write(_sessions_dir() / f"{sid}.json",
                      json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def load_session(sid: str) -> dict | None:
    p = _sessions_dir() / f"{sid}.json"
    if not p.is_file():
        return None
    data = _read_json(p)
    if not data:
        return None
    # 过期的顺手删掉，免得越积越多
    if time.time() - float(data.get("_saved_at") or 0) > SESSION_MAX_AGE:
        try:
            p.unlink()
        except OSError:
            pass
        return None
    return data


def prune_sessions() -> int:
    """启动时清一次：超期的删、超量的按时间淘汰最旧的。返回删除条数。"""
    d = _sessions_dir()
    files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = 0
    now = time.time()
    for i, f in enumerate(files):
        try:
            too_old = now - f.stat().st_mtime > SESSION_MAX_AGE
            too_many = i >= MAX_SESSIONS
            if too_old or too_many:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed
