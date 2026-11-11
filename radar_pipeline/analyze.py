"""分析层：只读库，产出给报告用的小结。"""
from __future__ import annotations

from . import clean

_MISSING = object()  # 区分“调用方没传 previous_titles”和“首次运行（传 None）”


def new_topics(conn, previous_titles, limit: int = 15):
    """本次库里有、上次快照里没有的话题。

    previous_titles 为 None 表示首次运行、无快照可比，返回 None；
    否则返回 [(title, url), ...]，热榜按热度排在前，AI 区随后。
    """
    if previous_titles is None:
        return None
    seen = set(previous_titles)
    out = []
    for norm, title, url, _hot in conn.execute(
        "SELECT normalized_title, MIN(title), MIN(url), MAX(hot_value) "
        "FROM hot_items GROUP BY normalized_title ORDER BY MAX(hot_value) DESC"
    ):
        if (norm or "") not in seen:
            out.append((title, url))
        if len(out) >= limit:
            return out
    for title, url in conn.execute("SELECT title, url FROM ai_items ORDER BY id"):
        if clean.normalize_title(title) not in seen:
            out.append((title, url))
        if len(out) >= limit:
            break
    return out


def cross_platform_topics(conn, limit: int = 10):
    """跨平台热议话题：标题 + 出现平台数 + 各平台最高热度。"""
    return conn.execute(
        """SELECT normalized_title, MIN(title) AS title,
                  COUNT(DISTINCT platform) AS platforms,
                  GROUP_CONCAT(DISTINCT platform) AS platform_list,
                  MAX(hot_value) AS max_hot
           FROM hot_items WHERE cross_platform = 1
           GROUP BY normalized_title
           ORDER BY platforms DESC, max_hot DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def platform_counts(conn):
    return conn.execute(
        "SELECT platform, COUNT(*) FROM hot_items GROUP BY platform ORDER BY 2 DESC"
    ).fetchall()


def top_ai_models(conn, limit: int = 10):
    return conn.execute(
        """SELECT title, url, score, extra FROM ai_items
           WHERE kind = 'model' ORDER BY score DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def latest_papers(conn, limit: int = 10):
    return conn.execute(
        """SELECT title, url, source, published_at FROM ai_items
           WHERE kind = 'paper' ORDER BY published_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def build_report(conn, fetched_at: str, metrics=None, previous_titles=_MISSING) -> str:
    """生成 Markdown 报告正文。

    metrics（可选）：{"hot": {"fetched","duplicates","dropped","stored"},
    "ai": {...}, "sources": [{"name","status","rows","error"}]}，写进报告顶部。
    previous_titles（可选）：上次快照的话题集合；None 表示首次运行；
    不传则不渲染“今日新增话题”一节。
    """
    lines = [f"# 热点雷达日报（{fetched_at}）", ""]
    if metrics:
        hot, ai = metrics["hot"], metrics["ai"]
        sources = metrics["sources"]
        ok = sum(1 for s in sources if s["status"] == "ok")
        lines.append("## 本次运行")
        lines.append(f"- 数据源：{len(sources)} 个，成功 {ok} 个，失败 {len(sources) - ok} 个")
        lines.append(
            f"- 热榜：抓到 {hot['fetched']} 条，去重 {hot['duplicates']} 条，"
            f"丢弃 {hot['dropped']} 条，入库 {hot['stored']} 条")
        lines.append(
            f"- AI 区：抓到 {ai['fetched']} 条，去重 {ai['duplicates']} 条，"
            f"丢弃 {ai['dropped']} 条，入库 {ai['stored']} 条")
        failed = [s for s in sources if s["status"] == "failed"]
        if failed:
            lines.append("- 失败的源（已保留上次快照）：")
            for s in failed:
                lines.append(f"  - {s['name']}: {s['error']}")
        lines.append("")
    if previous_titles is not _MISSING:
        topics = new_topics(conn, previous_titles)
        lines.append("## 今日新增话题")
        if topics is None:
            lines.append("- 首次运行，尚无上次快照可对比。")
        elif topics:
            for title, url in topics:
                lines.append(f"- [{title}]({url})")
        else:
            lines.append("- 与上次快照相比没有新话题。")
        lines.append("")
    topics = cross_platform_topics(conn)
    lines.append("## 跨平台热议")
    if topics:
        for _, title, n, plist, hot in topics:
            lines.append(f"- {title}（{n} 个平台：{plist}，最高热度 {hot or '—'}）")
    else:
        lines.append("- 本次没有跨平台同题（或热榜源失败，见刷新日志）。")
    lines += ["", "## 各平台条数"]
    for platform, n in platform_counts(conn):
        lines.append(f"- {platform}：{n} 条")
    lines += ["", "## AI 趋势模型 Top 10"]
    for title, url, score, extra in top_ai_models(conn):
        lines.append(f"- [{title}]({url})（trendingScore {score}，{extra}）")
    lines += ["", "## 最新论文"]
    for title, url, source, pub in latest_papers(conn):
        lines.append(f"- [{title}]({url})（{source}，{pub or '时间未知'}）")
    lines += ["", "_数据来源见 docs/SOURCES.md；失败源保留上次快照，报告不编数据。_"]
    return "\n".join(lines) + "\n"
