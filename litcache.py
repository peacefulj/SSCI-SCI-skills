# -*- coding: utf-8 -*-
"""文献检索缓存 —— 本地 SQLite，跨进程/跨重启有效。

**为什么需要**

论文装配阶段同一条检索词会被反复查（写作→返查→引用核查），而学术 API
本身限流且偶发故障。缓存带来三个直接收益：

1. 命中从「秒级网络往返」变成「毫秒级本地读」；
2. 少发请求 = 更少触发 429，反之也保护了对方服务；
3. 网络整体不可用（或限流严重）时，仍能拿历史结果把装配跑完，
   而不是留下满屏 `[CITE: ...]` 占位。

**设计取舍**

- 只缓存**原始记录列表**，不缓存「匹配判定结果」：挑哪一条仍由 `pick()`
  现算。这样即便术语/门槛规则改了，也不会读到按旧规则判好的陈旧结论。
- 键含 `source`，OpenAlex 与 Crossref 的结果不互相污染。
- 空结果也缓存（`n=0`），否则查不到的词会被反复重查。
- 负缓存（查不到）TTL 短于正缓存（查到了）。
- **任何缓存异常都不抛给调用方**：缓存是优化，不能成为新的故障点。
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

# 正缓存 30 天：文献库每天在变，但「某检索词对应哪批论文」几周内基本稳定。
TTL_HIT = 30 * 86400
# 负缓存 3 天：今天查不到，可能是对方抽风；过几天要允许重查。
TTL_MISS = 3 * 86400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS qcache (
    key      TEXT PRIMARY KEY,
    source   TEXT NOT NULL,
    payload  TEXT NOT NULL,
    n        INTEGER NOT NULL,
    ts       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qcache_ts ON qcache(ts);
"""


def _db_path() -> Path | None:
    """缓存库位置。取不到可写目录时返回 None（调用方直接跳过缓存）。"""
    try:
        import paths  # 延迟导入：本模块可被独立脚本复用
        p = paths.cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        return None


def _connect(path: Path) -> sqlite3.Connection:
    # timeout=3：并发时别卡死主流程，宁可拿不到缓存
    conn = sqlite3.connect(str(path), timeout=3)
    conn.execute("PRAGMA journal_mode=WAL")      # 读写并发友好
    conn.executescript(_SCHEMA)
    return conn


def make_key(source: str, query: str, per_page: int) -> str:
    """缓存键。

    检索词先做归一化（小写 + 折叠空白）：模型两次生成的检索式常常只差大小写
    或空格，不归一就会重复打网络。用 repr 而非 hash：可读、无碰撞风险。
    """
    q = " ".join((query or "").split()).lower()
    return f"{source}|{q}|{int(per_page)}"


def get(source: str, query: str, per_page: int) -> list[dict] | None:
    """取缓存。返回 None 表示「没缓存」，返回 [] 表示「缓存了空结果」。"""
    path = _db_path()
    if not path:
        return None
    key = make_key(source, query, per_page)
    try:
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT payload, n, ts FROM qcache WHERE key=?", (key,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        payload, n, ts = row
        ttl = TTL_HIT if n else TTL_MISS
        if time.time() - ts > ttl:
            return None
        data = json.loads(payload)
        return data if isinstance(data, list) else None
    except Exception:
        return None


def put(source: str, query: str, per_page: int, items: list[dict]) -> None:
    """写缓存。失败静默——缓存不能拖累主流程。"""
    path = _db_path()
    if not path:
        return
    key = make_key(source, query, per_page)
    try:
        payload = json.dumps(items or [], ensure_ascii=False)
        conn = _connect(path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO qcache(key, source, payload, n, ts) "
                "VALUES(?,?,?,?,?)",
                (key, source, payload, len(items or []), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def stats() -> dict:
    """缓存概况，供自检/排查用。"""
    path = _db_path()
    if not path or not path.exists():
        return {"enabled": False, "entries": 0}
    try:
        conn = _connect(path)
        try:
            total, hits = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(n>0),0) FROM qcache"
            ).fetchone()
        finally:
            conn.close()
        return {"enabled": True, "path": str(path),
                "entries": int(total or 0), "with_results": int(hits or 0)}
    except Exception as e:
        return {"enabled": False, "error": str(e)}


def clear() -> int:
    """清空缓存，返回删除条数。"""
    path = _db_path()
    if not path or not path.exists():
        return 0
    try:
        conn = _connect(path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM qcache").fetchone()[0]
            conn.execute("DELETE FROM qcache")
            conn.commit()
        finally:
            conn.close()
        return int(n or 0)
    except Exception:
        return 0
