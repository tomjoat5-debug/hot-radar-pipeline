"""入库层：SQLite。快照按 source 全量替换（表体积有界），日志只留最近 50 条。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS hot_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    rank INTEGER,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    hot_value INTEGER,
    source_updated_at TEXT,
    normalized_title TEXT,
    cross_platform INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    score INTEGER,
    extra TEXT,
    source TEXT NOT NULL,
    published_at TEXT,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    dropped INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    fetched_at TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def store_hot_items(conn, rows, fetched_at: str | None = None):
    """按 platform 分组替换：只删本次成功拉到的平台的旧快照，失败的平台保留旧数据。"""
    fetched_at = fetched_at or _now()
    platforms = sorted({r["platform"] for r in rows})
    with conn:
        for platform in platforms:
            conn.execute("DELETE FROM hot_items WHERE platform = ?", (platform,))
        conn.executemany(
            """INSERT INTO hot_items
               (platform, rank, title, url, hot_value, source_updated_at,
                normalized_title, cross_platform, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["platform"], r["rank"], r["title"], r["url"], r["hot_value"],
              r["source_updated_at"], r["normalized_title"], r["cross_platform"],
              fetched_at) for r in rows],
        )
    return len(rows)


def store_ai_items(conn, rows, fetched_at: str | None = None):
    fetched_at = fetched_at or _now()
    kinds_sources = sorted({(r["kind"], r["source"]) for r in rows})
    with conn:
        for kind, source in kinds_sources:
            conn.execute(
                "DELETE FROM ai_items WHERE kind = ? AND source = ?", (kind, source))
        conn.executemany(
            """INSERT INTO ai_items
               (kind, title, url, score, extra, source, published_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["kind"], r["title"], r["url"], r["score"], r["extra"],
              r["source"], r["published_at"], fetched_at) for r in rows],
        )
    return len(rows)


def log_refresh(conn, source, status, rows=0, dropped=0, message=""):
    with conn:
        conn.execute(
            """INSERT INTO refresh_log
               (source, status, rows, dropped, message, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source, status, rows, dropped, message[:500], _now()),
        )
        conn.execute(
            "DELETE FROM refresh_log WHERE id NOT IN "
            "(SELECT id FROM refresh_log ORDER BY id DESC LIMIT 50)"
        )


def counts(conn):
    return {
        "hot_items": conn.execute("SELECT COUNT(*) FROM hot_items").fetchone()[0],
        "ai_items": conn.execute("SELECT COUNT(*) FROM ai_items").fetchone()[0],
        "cross_platform": conn.execute(
            "SELECT COUNT(DISTINCT normalized_title) FROM hot_items "
            "WHERE cross_platform = 1").fetchone()[0],
    }
