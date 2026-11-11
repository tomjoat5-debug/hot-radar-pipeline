"""清洗层：标题归一化、去重、跨平台同题打标、hot_value 转数字。

纯函数，方便单测；不联网。
"""
from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_title(title: str) -> str:
    """去标点、去空白、全小写。只用于匹配，不改原始标题。"""
    return _PUNCT.sub("", title).lower()


def to_int(value):
    """hot_value 转 int，转不了返回 None（不断整条）。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def clean_hot_items(rows):
    """清洗热榜行。

    返回 (cleaned, dropped)：cleaned 每行带 normalized_title / hot_value_int /
    cross_platform（0/1）；dropped 是丢弃数（缺标题或缺链接）。
    """
    cleaned, dropped = [], []
    seen = set()
    for row in rows:
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        if not title or not url:
            dropped.append(row)
            continue
        key = (row.get("platform"), normalize_title(title))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "platform": row.get("platform"),
            "rank": to_int(row.get("rank")),
            "title": title,
            "url": url,
            "hot_value": to_int(row.get("hot_value")),
            "source_updated_at": row.get("source_updated_at"),
            "normalized_title": normalize_title(title),
            "cross_platform": 0,
        })
    # 同一归一化标题出现在 >=2 个平台 -> 跨平台热议
    platforms_by_title = {}
    for row in cleaned:
        platforms_by_title.setdefault(row["normalized_title"], set()).add(row["platform"])
    for row in cleaned:
        if len(platforms_by_title[row["normalized_title"]]) >= 2:
            row["cross_platform"] = 1
    return cleaned, len(dropped)


def clean_ai_items(rows):
    """清洗 AI 区行：只去缺标题/缺链接的，其余原样保留。"""
    cleaned, dropped = [], 0
    seen = set()
    for row in rows:
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        if not title or not url:
            dropped += 1
            continue
        key = (row.get("kind"), row.get("source"), normalize_title(title))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "kind": row.get("kind"),
            "title": title,
            "url": url,
            "score": to_int(row.get("score")) if row.get("score") is not None else None,
            "extra": (row.get("extra") or "")[:500],
            "source": row.get("source"),
            "published_at": row.get("published_at"),
        })
    return cleaned, dropped
