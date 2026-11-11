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

    # 1. 采集
    hot_by_platform, hot_errors = sources.fetch_all_hotboards(args.hot_limit)
    ai_rows, ai_errors = [], {}
    for fetcher in (sources.fetch_hf_models, sources.fetch_hf_papers,
                    sources.fetch_hn_top, sources.fetch_github_trending,
                    sources.fetch_arxiv):
        rows, err = fetcher()
        ai_rows.extend(rows)
        if err:
            ai_errors[err.split(":")[0]] = err
    rss_rows, rss_errors = sources.fetch_rss()
    ai_rows.extend(rss_rows)
    ai_errors.update(rss_errors)

    # 2. 清洗
    all_hot = [r for rows in hot_by_platform.values() for r in rows]
    hot_clean, hot_dropped = clean.clean_hot_items(all_hot)
    ai_clean, ai_dropped = clean.clean_ai_items(ai_rows)

    # 3. 入库（只替换成功拉到的平台/分区，失败的保留旧快照）
    ok_platforms = [p for p in hot_by_platform if p not in hot_errors]
    store.store_hot_items(conn, [r for r in hot_clean if r["platform"] in ok_platforms],
                          fetched_at)
    store.store_ai_items(conn, ai_clean, fetched_at)

    # 4. 日志
    for platform, rows in hot_by_platform.items():
        if platform in hot_errors:
            store.log_refresh(conn, f"hotboard:{platform}", "failed", 0, 0,
                              hot_errors[platform])
        else:
            store.log_refresh(conn, f"hotboard:{platform}", "ok", len(rows), 0, "")
    for name, err in ai_errors.items():
        store.log_refresh(conn, name, "failed", 0, 0, err)
    store.log_refresh(conn, "ai:all", "ok", len(ai_clean), ai_dropped, "")

    # 5. 报告
    total = store.counts(conn)
    print(f"热榜：{len(hot_clean)} 条入库（丢弃 {hot_dropped}），"
          f"AI 区：{len(ai_clean)} 条入库（丢弃 {ai_dropped}）")
    print(f"库内合计：热榜 {total['hot_items']} 条，AI {total['ai_items']} 条，"
          f"跨平台话题 {total['cross_platform']} 个")
    if hot_errors or ai_errors:
        print("失败的源（已保留上次快照）：")
        for err in list(hot_errors.values()) + list(ai_errors.values()):
            print(f"  - {err}")

    if not args.no_report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(analyze.build_report(conn, fetched_at), encoding="utf-8")
        print(f"报告已写到 {report_path}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
