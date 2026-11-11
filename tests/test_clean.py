"""清洗与分析逻辑单测：不联网。"""
import sqlite3
import unittest

from radar_pipeline import analyze, clean, store


class TestClean(unittest.TestCase):
    def test_normalize_ignores_punctuation_and_case(self):
        self.assertEqual(clean.normalize_title("金鸡奖！获奖名单 "),
                         clean.normalize_title("金鸡奖获奖名单"))
        self.assertEqual(clean.normalize_title("Hello World"),
                         clean.normalize_title("hello, world!"))

    def test_cross_platform_flag(self):
        rows = [
            {"platform": "weibo", "rank": 1, "title": "金鸡奖获奖名单",
             "url": "https://x/1", "hot_value": "100", "source_updated_at": None},
            {"platform": "zhihu", "rank": 2, "title": "金鸡奖获奖名单！",
             "url": "https://x/2", "hot_value": "90", "source_updated_at": None},
            {"platform": "baidu", "rank": 1, "title": "只有这里有",
             "url": "https://x/3", "hot_value": "50", "source_updated_at": None},
        ]
        cleaned, dropped = clean.clean_hot_items(rows)
        self.assertEqual(dropped, 0)
        by_title = {r["normalized_title"]: r for r in cleaned}
        self.assertEqual(by_title["金鸡奖获奖名单"]["cross_platform"], 1)
        self.assertEqual(by_title["只有这里有"]["cross_platform"], 0)

    def test_dedupe_and_drop(self):
        rows = [
            {"platform": "weibo", "rank": 1, "title": "重复标题",
             "url": "https://x/1", "hot_value": "10", "source_updated_at": None},
            {"platform": "weibo", "rank": 2, "title": "重复标题",
             "url": "https://x/2", "hot_value": "9", "source_updated_at": None},
            {"platform": "weibo", "rank": 3, "title": "",
             "url": "https://x/3", "hot_value": "8", "source_updated_at": None},
            {"platform": "weibo", "rank": 4, "title": "没链接",
             "url": "", "hot_value": "7", "source_updated_at": None},
        ]
        cleaned, dropped = clean.clean_hot_items(rows)
        self.assertEqual(len(cleaned), 1)  # 同平台去重后只留 rank 1
        self.assertEqual(cleaned[0]["rank"], 1)
        self.assertEqual(dropped, 2)

    def test_hot_value_unparsable_becomes_none(self):
        self.assertIsNone(clean.to_int("1.2万"))
        self.assertEqual(clean.to_int("1,234"), 1234)
        self.assertIsNone(clean.to_int(None))


class TestStoreAnalyze(unittest.TestCase):
    def test_snapshot_replace_keeps_other_platforms(self):
        conn = store.connect(":memory:")
        rows, _ = clean.clean_hot_items([
            {"platform": "weibo", "rank": 1, "title": "A",
             "url": "https://x/a", "hot_value": "5", "source_updated_at": None},
            {"platform": "zhihu", "rank": 1, "title": "B",
             "url": "https://x/b", "hot_value": "6", "source_updated_at": None},
        ])
        store.store_hot_items(conn, rows)
        # 只替换微博快照，知乎旧数据应保留
        rows2, _ = clean.clean_hot_items([
            {"platform": "weibo", "rank": 1, "title": "A2",
             "url": "https://x/a2", "hot_value": "7", "source_updated_at": None},
        ])
        store.store_hot_items(conn, rows2)
        titles = [r[0] for r in conn.execute("SELECT title FROM hot_items")]
        self.assertCountEqual(titles, ["A2", "B"])
        self.assertEqual(store.counts(conn)["hot_items"], 2)

    def test_cross_platform_topics(self):
        conn = store.connect(":memory:")
        rows, _ = clean.clean_hot_items([
            {"platform": "weibo", "rank": 1, "title": "同题",
             "url": "https://x/1", "hot_value": "5", "source_updated_at": None},
            {"platform": "zhihu", "rank": 1, "title": "同题",
             "url": "https://x/2", "hot_value": "6", "source_updated_at": None},
        ])
        store.store_hot_items(conn, rows)
        topics = analyze.cross_platform_topics(conn)
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0][2], 2)  # 2 个平台


if __name__ == "__main__":
    unittest.main()
