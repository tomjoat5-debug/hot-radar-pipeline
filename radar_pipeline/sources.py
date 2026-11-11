"""采集层：只接已实测的免注册、免 Key 公开接口。

来源与实测记录见 docs/SOURCES.md。每个采集函数返回 (rows, error)，
error 为 None 表示成功；失败时 rows 为空，调用方记 refresh_log 后继续跑别的源。
"""
from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "hot-radar-pipeline/0.1 (+https://github.com/)"}
TIMEOUT = 20

# UAPI 热榜聚合：11 个平台，免 Key
UAPI_PLATFORMS = [
    "weibo", "zhihu", "baidu", "bilibili", "douyin",
    "toutiao", "kuaishou", "xiaohongshu", "thepaper", "36kr", "ithome",
]
UAPI_URL = "https://uapis.cn/api/v1/misc/hotboard?type={platform}"

HF_TRENDING = (
    "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=15"
)
HF_PAPERS = "https://huggingface.co/api/daily_papers?limit=10"
HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

RSS_SOURCES = [
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("IT之家", "https://www.ithome.com/rss/"),
    ("量子位", "https://www.qbitai.com/feed"),
]
ARXIV_URL = (
    "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL"
    "&sortBy=submittedDate&sortOrder=descending&max_results=8"
)


def _get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_hotboard(platform: str, limit: int = 30):
    """单个平台热榜。返回 (rows, error)。"""
    try:
        data = _get_json(UAPI_URL.format(platform=platform))
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return [], f"{platform}: {exc}"
    rows = []
    for item in (data.get("list") or [])[:limit]:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        rows.append({
            "platform": platform,
            "rank": item.get("index"),
            "title": title,
            "url": url,
            "hot_value": item.get("hot_value"),
            "source_updated_at": data.get("update_time"),
        })
    return rows, None


def fetch_all_hotboards(limit: int = 30):
    """11 个平台热榜。返回 {platform: rows} 与 {platform: error}。"""
    all_rows, errors = {}, {}
    for platform in UAPI_PLATFORMS:
        rows, err = fetch_hotboard(platform, limit)
        all_rows[platform] = rows
        if err:
            errors[platform] = err
    return all_rows, errors


def fetch_hf_models(limit: int = 15):
    try:
        data = _get_json(HF_TRENDING)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return [], f"huggingface-models: {exc}"
    rows = []
    for m in data[:limit]:
        rows.append({
            "kind": "model",
            "title": m.get("id", ""),
            "url": f"https://huggingface.co/{m.get('id', '')}",
            "score": m.get("trendingScore"),
            "extra": f"{m.get('pipeline_tag') or ''} | likes {m.get('likes')} | downloads {m.get('downloads')}",
            "source": "Hugging Face",
            "published_at": m.get("createdAt"),
        })
    return [r for r in rows if r["title"]], None


def fetch_hf_papers(limit: int = 10):
    try:
        data = _get_json(HF_PAPERS)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return [], f"huggingface-papers: {exc}"
    rows = []
    for p in data[:limit]:
        paper = p.get("paper") or {}
        rows.append({
            "kind": "paper",
            "title": paper.get("title", ""),
            "url": f"https://huggingface.co/papers/{paper.get('id', '')}",
            "score": None,
            "extra": ", ".join(a.get("name", "") for a in paper.get("authors", [])[:3]),
            "source": "Hugging Face Daily Papers",
            "published_at": paper.get("publishedAt"),
        })
    return [r for r in rows if r["title"]], None


def fetch_hn_top(limit: int = 12, fetch_ids: int = 30):
    try:
        ids = _get_json(HN_TOP)[:fetch_ids]
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return [], f"hackernews: {exc}"
    rows = []
    for story_id in ids:
        try:
            item = _get_json(HN_ITEM.format(id=story_id))
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError):
            continue
        if not item.get("title"):
            continue
        rows.append({
            "kind": "tech",
            "title": item["title"],
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
            "score": item.get("score"),
            "extra": "",
            "source": "Hacker News",
            "published_at": (
                datetime.fromtimestamp(item["time"], tz=timezone.utc).isoformat()
                if item.get("time") else None
            ),
        })
        if len(rows) >= limit:
            break
    return rows, None


def fetch_github_trending(limit: int = 10):
    """最近 7 天新建、stars 较高的 AI 相关仓库。未认证限额 60 次/小时，够一次运行用。"""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    q = f"created:>{since}+stars:>50+ai"
    url = (
        "https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={limit}"
    )
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return [], f"github-search: {exc}"
    rows = []
    for r in data.get("items") or []:
        rows.append({
            "kind": "oss",
            "title": r.get("full_name", ""),
            "url": r.get("html_url", ""),
            "score": r.get("stargazers_count"),
            "extra": (r.get("description") or "")[:200],
            "source": "GitHub",
            "published_at": r.get("created_at"),
        })
    return rows, None


def _parse_rss(text: str, source: str, limit: int = 10):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows = []
    for entry in root.iter("item"):
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        if title and link:
            rows.append({
                "kind": "news",
                "title": title,
                "url": link,
                "score": None,
                "extra": "",
                "source": source,
                "published_at": entry.findtext("pubDate"),
            })
    if not rows:  # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = (link_el.get("href") if link_el is not None else "").strip()
            if title and link:
                rows.append({
                    "kind": "news",
                    "title": title,
                    "url": link,
                    "score": None,
                    "extra": "",
                    "source": source,
                    "published_at": entry.findtext("a:updated", namespaces=ns),
                })
    return rows[:limit]


def fetch_rss(limit: int = 10):
    rows, errors = [], {}
    for source, url in RSS_SOURCES:
        try:
            rows.extend(_parse_rss(_get_text(url), source, limit))
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            errors[source] = f"rss-{source}: {exc}"
    return rows, errors


def fetch_arxiv(limit: int = 8):
    try:
        text = _get_text(ARXIV_URL)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        return [], f"arxiv: {exc}"
    rows = _parse_rss(text, "arXiv", limit)
    for r in rows:
        r["kind"] = "paper"
    return rows, None
