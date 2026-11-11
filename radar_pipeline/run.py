"""入口：采集 → 清洗 → 入库 → 分析出报告。

单个源失败不中断整次运行，失败源保留上次快照并记 refresh_log。
用法：python -m radar_pipeline.run [--db data/radar.db] [--report reports/latest.md]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, clean, sources, store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="全网热点雷达数据管道")
    parser.add_argument("--db", default="data/radar.db")
    parser.add_argument("--report", default="reports/latest.md")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--hot-limit", type=int, default=30)
    args = parser.parse_args(argv)

    fetched_at = datetime.now(timezone.utc).isoformat()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(str(db_path))

    # 0. 上次快照（入库前抓取，用于报告里的“今日新增话题”）；
    #    库里没有任何数据时记为首次运行（None）。
    prev = store.counts(conn)
    if prev["hot_items"] + prev["ai_items"] == 0:
        previous_titles = None
    else:
        previous_titles = {
            (r[0] or "") for r in conn.execute(
                "SELECT normalized_title FROM hot_items")
        } | {
            clean.normalize_title(r[0]) for r in conn.execute(
                "SELECT title FROM ai_items")
        }

    # 1. 采集
    hot_by_platform, hot_errors = sources.fetch_all_hotboards(args.hot_limit)
    ai_rows = []
    ai_metrics = []
    for name, fetcher in (
        ("huggingface-models", sources.fetch_hf_models),
        ("huggingface-papers", sources.fetch_hf_papers),
        ("hackernews", sources.fetch_hn_top),
        ("github-search", sources.fetch_github_trending),
        ("arxiv", sources.fetch_arxiv),
    ):
        rows, err = fetcher()
        ai_rows.extend(rows)
        ai_metrics.append({"name": name, "status": "failed" if err else "ok",
                           "rows": len(rows), "error": err or ""})
    rss_rows, rss_errors, rss_counts = sources.fetch_rss()
    ai_rows.extend(rss_rows)
    for source, _url in sources.RSS_SOURCES:
        err = rss_errors.get(source)
        ai_metrics.append({"name": f"rss:{source}",
                           "status": "failed" if err else "ok",
                           "rows": rss_counts.get(source, 0),
                           "error": err or ""})

    # 2. 清洗
    all_hot = [r for rows in hot_by_platform.values() for r in rows]
    hot_clean, hot_dropped = clean.clean_hot_items(all_hot)
    ai_clean, ai_dropped = clean.clean_ai_items(ai_rows)

    # 3. 入库（只替换成功拉到的平台/分区，失败的保留旧快照）
    ok_platforms = [p for p in hot_by_platform if p not in hot_errors]
    hot_stored = [r for r in hot_clean if r["platform"] in ok_platforms]
    store.store_hot_items(conn, hot_stored, fetched_at)
    store.store_ai_items(conn, ai_clean, fetched_at)

    # 运行指标：各源成功/失败、抓取条数、去重数、丢弃数、入库数
    hot_metrics = [{"name": p, "status": "failed" if p in hot_errors else "ok",
                    "rows": len(rows), "error": hot_errors.get(p, "")}
                   for p, rows in hot_by_platform.items()]
    metrics = {
        "hot": {"fetched": len(all_hot),
                "duplicates": len(all_hot) - hot_dropped - len(hot_clean),
                "dropped": hot_dropped, "stored": len(hot_stored)},
        "ai": {"fetched": len(ai_rows),
               "duplicates": len(ai_rows) - ai_dropped - len(ai_clean),
               "dropped": ai_dropped, "stored": len(ai_clean)},
        "sources": hot_metrics + ai_metrics,
    }

    # 4. 日志
    for platform, rows in hot_by_platform.items():
        if platform in hot_errors:
            store.log_refresh(conn, f"hotboard:{platform}", "failed", 0, 0,
                              hot_errors[platform])
        else:
            store.log_refresh(conn, f"hotboard:{platform}", "ok", len(rows), 0, "")
    for entry in ai_metrics:
        if entry["status"] == "failed":
            store.log_refresh(conn, entry["name"], "failed", 0, 0, entry["error"])
    store.log_refresh(conn, "ai:all", "ok", len(ai_clean), ai_dropped, "")

    # 5. 报告
    total = store.counts(conn)
    print(f"热榜：{len(hot_clean)} 条入库（丢弃 {hot_dropped}），"
          f"AI 区：{len(ai_clean)} 条入库（丢弃 {ai_dropped}）")
    print(f"库内合计：热榜 {total['hot_items']} 条，AI {total['ai_items']} 条，"
          f"跨平台话题 {total['cross_platform']} 个")
    failed = [s for s in metrics["sources"] if s["status"] == "failed"]
    if failed:
        print("失败的源（已保留上次快照）：")
        for s in failed:
            print(f"  - {s['name']}: {s['error']}")

    if not args.no_report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            analyze.build_report(conn, fetched_at, metrics, previous_titles),
            encoding="utf-8")
        print(f"报告已写到 {report_path}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
