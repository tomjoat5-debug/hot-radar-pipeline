"""端到端单测：采集层全部 mock，跑一次完整流水线到临时目录。

断言报告与数据库生成、增量对比、失败源保留旧快照。不联网。
"""
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from radar_pipeline import run, sources


def hot_row(platform, title, rank=1):
    return {"platform": platform, "rank": rank, "title": title,
            "url": f"https://x/{platform}/{rank}", "hot_value": "100",
            "source_updated_at": None}


def ai_row(kind, title, source="Hugging Face"):
    return {"kind": kind, "title": title, "url": f"https://x/{title}",
            "score": 10, "extra": "", "source": source,
            "published_at": None}


class TestRunEndToEnd(unittest.TestCase):
    def _patched_run(self, tmp, hotboards, hot_errors=None,
                     hf_models=(), hf_papers=(), hn=(), gh=(), arxiv=(),
                     rss=()):
        """在 mock 采集下跑一次 main，返回 (rc, report_text, db_path)。"""
        db_path = Path(tmp) / "data" / "radar.db"
        report_path = Path(tmp) / "reports" / "latest.md"
        rss_counts = {s: 0 for s, _ in sources.RSS_SOURCES}
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                sources, "fetch_all_hotboards",
                return_value=(hotboards, hot_errors or {})))
            stack.enter_context(patch.object(
                sources, "fetch_hf_models",
                return_value=(list(hf_models), None)))
            stack.enter_context(patch.object(
                sources, "fetch_hf_papers",
                return_value=(list(hf_papers), None)))
            stack.enter_context(patch.object(
                sources, "fetch_hn_top", return_value=(list(hn), None)))
            stack.enter_context(patch.object(
                sources, "fetch_github_trending",
                return_value=(list(gh), None)))
            stack.enter_context(patch.object(
                sources, "fetch_arxiv", return_value=(list(arxiv), None)))
            stack.enter_context(patch.object(
                sources, "fetch_rss",
                return_value=(list(rss), {}, rss_counts)))
            rc = run.main(["--db", str(db_path), "--report", str(report_path)])
        return rc, report_path.read_text(encoding="utf-8"), db_path

    def test_first_run_generates_report_and_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, report, db_path = self._patched_run(
                tmp,
                {"weibo": [hot_row("weibo", "话题A")],
                 "zhihu": [hot_row("zhihu", "话题B")]},
                hf_models=[ai_row("model", "org/m1")])
            self.assertEqual(rc, 0)
            self.assertIn("## 本次运行", report)
            self.assertIn("首次运行", report)
            self.assertIn("抓到 2 条", report)
            self.assertIn("去重 0 条", report)
            conn = sqlite3.connect(db_path)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM hot_items").fetchone()[0], 2)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM ai_items").fetchone()[0], 1)

    def test_second_run_lists_only_new_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._patched_run(
                tmp, {"weibo": [hot_row("weibo", "话题A"),
                                hot_row("weibo", "话题B")]})
            _rc, report, _db = self._patched_run(
                tmp, {"weibo": [hot_row("weibo", "话题B"),
                                hot_row("weibo", "话题C")]})
            self.assertNotIn("首次运行", report)
            self.assertIn("话题C", report)
            self.assertNotIn("话题B", report)  # 上次已有，不是新话题

    def test_second_run_no_new_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._patched_run(tmp, {"weibo": [hot_row("weibo", "话题A")]})
            _rc, report, _db = self._patched_run(
                tmp, {"weibo": [hot_row("weibo", "话题A")]})
            self.assertIn("没有新话题", report)

    def test_failed_source_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._patched_run(
                tmp, {"weibo": [hot_row("weibo", "话题A")],
                      "zhihu": [hot_row("zhihu", "话题B")]})
            _rc, report, db_path = self._patched_run(
                tmp, {"weibo": [], "zhihu": [hot_row("zhihu", "话题B2")]},
                hot_errors={"weibo": "weibo: boom"})
            self.assertIn("weibo: boom", report)
            conn = sqlite3.connect(db_path)
            titles = {r[0] for r in conn.execute("SELECT title FROM hot_items")}
            self.assertEqual(titles, {"话题A", "话题B2"})


if __name__ == "__main__":
    unittest.main()
