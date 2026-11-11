"""分析层：只读库，产出给报告用的小结。"""
from __future__ import annotations


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


def build_report(conn, fetched_at: str) -> str:
    """生成 Markdown 报告正文。"""
    lines = [f"# 热点雷达日报（{fetched_at}）", ""]
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
