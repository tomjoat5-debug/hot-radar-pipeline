"""采集层解析单测：只用本地 fixture，不联网。

网络调用（sources._get_json / _get_text）用 unittest.mock 替换，
测的是拿到原始数据后各采集函数的解析逻辑。
"""
import unittest
import urllib.error
from unittest.mock import patch

from radar_pipeline import sources

RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>News One</title><link>https://example.com/1</link>
<pubDate>Mon, 10 Nov 2026 08:00:00 GMT</pubDate></item>
<item><title>News Two</title><link>https://example.com/2</link>
<pubDate>Mon, 10 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title></title><link>https://example.com/3</link></item>
</channel></rss>
"""

ATOM_FIXTURE = """<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Paper Title</title>
<link href="https://arxiv.org/abs/2611.00001"/>
<updated>2026-11-09T18:00:00Z</updated><summary>abstract</summary></entry>
<entry><title>Second Paper</title>
<link href="https://arxiv.org/abs/2611.00002"/>
<updated>2026-11-09T17:00:00Z</updated></entry>
</feed>
"""


class TestParseRss(unittest.TestCase):
    def test_rss2_parses_items_and_skips_empty_title(self):
        rows = sources._parse_rss(RSS_FIXTURE, "Test Source")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "News One")
        self.assertEqual(rows[0]["url"], "https://example.com/1")
        self.assertEqual(rows[0]["kind"], "news")
        self.assertEqual(rows[0]["source"], "Test Source")

    def test_rss2_limit_respected(self):
        self.assertEqual(len(sources._parse_rss(RSS_FIXTURE, "X", limit=1)), 1)

    def test_atom_parses_link_href(self):
        rows = sources._parse_rss(ATOM_FIXTURE, "arXiv")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "https://arxiv.org/abs/2611.00001")
        self.assertEqual(rows[0]["published_at"], "2026-11-09T18:00:00Z")

    def test_malformed_xml_returns_empty(self):
        self.assertEqual(sources._parse_rss("<not xml", "X"), [])
        self.assertEqual(sources._parse_rss("", "X"), [])


class TestFetchersWithFixtures(unittest.TestCase):
    def test_fetch_hotboard(self):
        fixture = {
            "list": [
                {"title": "  A  ", "url": "https://a", "index": 1,
                 "hot_value": "100"},
                {"title": "", "url": "https://b", "index": 2, "hot_value": "5"},
                {"title": "C", "url": "", "index": 3},
            ],
            "update_time": "2026-11-11 10:00:00",
        }
        with patch.object(sources, "_get_json", return_value=fixture):
            rows, err = sources.fetch_hotboard("weibo")
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "A")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["source_updated_at"], "2026-11-11 10:00:00")

    def test_fetch_hotboard_network_error(self):
        with patch.object(sources, "_get_json",
                          side_effect=urllib.error.URLError("boom")):
            rows, err = sources.fetch_hotboard("weibo")
        self.assertEqual(rows, [])
        self.assertIn("weibo", err)

    def test_fetch_hf_models(self):
        fixture = [{"id": "org/model", "trendingScore": 100,
                    "pipeline_tag": "text-generation", "likes": 5,
                    "downloads": 10, "createdAt": "2026-01-01T00:00:00.000Z"}]
        with patch.object(sources, "_get_json", return_value=fixture):
            rows, err = sources.fetch_hf_models()
        self.assertIsNone(err)
        self.assertEqual(rows[0]["url"], "https://huggingface.co/org/model")
        self.assertIn("text-generation", rows[0]["extra"])
        self.assertIn("likes 5", rows[0]["extra"])

    def test_fetch_hf_papers(self):
        fixture = [{"paper": {"id": "2611.00001", "title": "Test Paper",
                              "authors": [{"name": "Ann"}, {"name": "Bob"}],
                              "publishedAt": "2026-11-09T00:00:00.000Z"}}]
        with patch.object(sources, "_get_json", return_value=fixture):
            rows, err = sources.fetch_hf_papers()
        self.assertIsNone(err)
        self.assertEqual(rows[0]["url"],
                         "https://huggingface.co/papers/2611.00001")
        self.assertEqual(rows[0]["extra"], "Ann, Bob")

    def test_fetch_hn_top(self):
        items = {
            11: {"title": "Story A", "url": "https://a.com", "score": 42,
                 "time": 1700000000},
            22: {"title": "Story B", "url": None, "score": 7,
                 "time": 1700000100},
        }
        with patch.object(sources, "_get_json",
                          side_effect=[[11, 22], items[11], items[22]]):
            rows, err = sources.fetch_hn_top()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["url"],
                         "https://news.ycombinator.com/item?id=22")

    def test_fetch_github_trending(self):
        fixture = {"items": [
            {"full_name": "a/b", "html_url": "https://github.com/a/b",
             "stargazers_count": 100, "description": "desc",
             "created_at": "2026-11-01T00:00:00Z"}]}
        with patch.object(sources, "_get_json", return_value=fixture):
            rows, err = sources.fetch_github_trending()
        self.assertIsNone(err)
        self.assertEqual(rows[0]["title"], "a/b")
        self.assertEqual(rows[0]["score"], 100)

    def test_fetch_arxiv(self):
        with patch.object(sources, "_get_text", return_value=ATOM_FIXTURE):
            rows, err = sources.fetch_arxiv()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["kind"] == "paper" for r in rows))
        self.assertTrue(all(r["source"] == "arXiv" for r in rows))

    def test_fetch_rss_all_sources(self):
        with patch.object(sources, "_get_text", return_value=RSS_FIXTURE):
            rows, errors, counts = sources.fetch_rss()
        self.assertEqual(errors, {})
        self.assertEqual(len(rows), 2 * len(sources.RSS_SOURCES))
        self.assertTrue(all(n == 2 for n in counts.values()))

    def test_fetch_rss_error_records_per_source(self):
        with patch.object(sources, "_get_text",
                          side_effect=urllib.error.URLError("down")):
            rows, errors, counts = sources.fetch_rss()
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), len(sources.RSS_SOURCES))
        self.assertTrue(all(n == 0 for n in counts.values()))


if __name__ == "__main__":
    unittest.main()
