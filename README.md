# hot-radar-pipeline

[![CI](https://github.com/tomjoat5-debug/hot-radar-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/tomjoat5-debug/hot-radar-pipeline/actions/workflows/ci.yml)
[![Daily refresh](https://github.com/tomjoat5-debug/hot-radar-pipeline/actions/workflows/daily.yml/badge.svg)](https://github.com/tomjoat5-debug/hot-radar-pipeline/actions/workflows/daily.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#quick-start)

Every morning, finding out what the internet is talking about means opening Weibo, Zhihu, Bilibili, Douyin, Hacker News, Hugging Face… 10+ tabs before breakfast. That's the information-overload problem this project solves: it pulls the hot lists of 11 Chinese platforms plus AI trends — trending Hugging Face models, daily papers, Hacker News, trending GitHub repos, AI news RSS, arXiv — into one place, and publishes a single daily report you can read in one glance. No accounts, no API keys, no paid services.

**中文简介**：每天要刷十几个平台才知道全网在聊什么，信息过载。这个项目把 11 个平台热榜 + AI 趋势（HF 模型、论文、HN、GitHub、RSS、arXiv）收进一个地方，每天出一份报告，一眼看完。纯 Python 标准库，零第三方依赖；GitHub Actions 每天自动跑、自动更新报告。

## What it does

```
collect (sources.py) → clean (clean.py) → store SQLite (store.py) → analyze → report (analyze.py)
   11 platform hot lists    normalize titles,     hot_items / ai_items     cross-platform topics
   HF models + papers       de-duplicate,        refresh_log (per-source   per-platform counts
   Hacker News / GitHub     cross-platform flag   success/failure)         top AI models, papers
   RSS (4 feeds) / arXiv    hot_value → int                                + run metrics & new topics
```

- **Collect** — 11 platform hot lists via UAPI (no key), Hugging Face trending models (15) & daily papers (10), Hacker News top stories (12), GitHub trending AI repos (10), 4 AI news RSS feeds, arXiv cs.AI/cs.CL (8).
- **Clean** — title normalization, de-duplication (keeps the lowest rank), cross-platform flag when the same story appears on ≥2 platforms, `hot_value` parsed to int (unparsable → NULL, row kept).
- **Store** — SQLite, three tables (`hot_items`, `ai_items`, `refresh_log`). Snapshots are replaced per source, so if one source fails, yesterday's data for it stays instead of being wiped.
- **Analyze & report** — cross-platform topics, per-platform counts, top AI models, latest papers, plus a run-metrics header (per-source success/failure, fetched/de-duplicated/dropped/stored counts) and a **new-topics-today** section that diffs against the previous snapshot. Output: `reports/latest.md`.

## Quick start

```bash
# Python 3.10+, zero third-party dependencies
python -m radar_pipeline.run

# Collect + store only, no report
python -m radar_pipeline.run --no-report

# Custom database / report location
python -m radar_pipeline.run --db data/radar.db --report reports/latest.md
```

Or with Docker (report and database kept on the host via volumes):

```bash
docker build -t hot-radar .
docker run --rm -v "$PWD/reports:/app/reports" -v "$PWD/data:/app/data" hot-radar
```

## How the daily automation works

`.github/workflows/daily.yml` runs the pipeline every day at 09:00 CST and commits the updated `reports/latest.md` back to this repo, so the report here is always fresh. The SQLite database is restored from `actions/cache` between runs so the "new topics today" diff works; if the cache is gone, the run degrades to a full fresh run (reported as a first run) and keeps going. `.github/workflows/ci.yml` runs the test suite on every push and pull request.

## Sample output

From `reports/latest.md` (2026-11-11 run, 292 hot items across 11 platforms):

```markdown
## 本次运行
- 数据源：20 个，成功 19 个，失败 1 个
- 热榜：抓到 292 条，去重 0 条，丢弃 0 条，入库 292 条
- AI 区：抓到 85 条，去重 0 条，丢弃 0 条，入库 85 条
- 失败的源（已保留上次快照）：
  - github-search: github-search: Remote end closed connection without response

## 今日新增话题
- [扬州江都发生3.9级地震](https://www.douyin.com/...)
- [人民空军成立77周年](https://www.douyin.com/...)
- ...

## 跨平台热议
- 梁家辉拒绝工作人员帮拿金鸡奖杯（3 个平台：weibo,baidu,toutiao，最高热度 7713096）
- 扬州地震（3 个平台：weibo,baidu,toutiao，最高热度 5983123）
```

Note the failed GitHub source in the header: the run kept going, kept the previous GitHub snapshot, and said so in the report instead of silently dropping it.

## Data sources

| Source | Endpoint | What it fetches |
| --- | --- | --- |
| UAPI hot lists | `uapis.cn/api/v1/misc/hotboard?type=<platform>` | 11 platforms (Weibo/Zhihu/Baidu/Bilibili/Douyin/Toutiao/Kuaishou/Xiaohongshu/The Paper/36Kr/ITHome), top 30 each |
| Hugging Face | `huggingface.co/api/models?sort=trendingScore…`, `…/api/daily_papers` | Trending models 15, daily papers 10 |
| Hacker News | `hacker-news.firebaseio.com/v0/topstories.json` + item API | Top 30 fetched, 12 kept |
| GitHub Search | `api.github.com/search/repositories?q=created:>last 7 days+stars:>50` | AI repos 10 (unauthenticated limit 60/hr, one call per run) |
| RSS | The Verge AI, OpenAI News, ITHome, QbitAI | Top 10 each |
| arXiv | `export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL…` | Latest 8 papers |

Full list, including sources that were tried and dropped, in [`docs/SOURCES.md`](docs/SOURCES.md).

## Tables

| Table | Contents | Update |
| --- | --- | --- |
| `hot_items` | Hot lists: platform / rank / title / url / hot_value / source_updated_at / fetched_at | Per-source snapshot replace, keeps the latest only |
| `ai_items` | AI: kind (model/paper/tech/oss/news) / title / url / score / source / published_at | Same, by kind+source |
| `refresh_log` | Per-source success/failure and row counts per run, last 50 rows | Append |

## Testing

```bash
python -m unittest discover -s tests -v
```

Tests use only the standard library and never touch the network: fixture JSON/XML for source parsing (`tests/test_sources.py`), boundary cases for cleaning (`tests/test_clean.py`), and a mocked end-to-end run into a temp directory (`tests/test_run.py`).

## Honest limitations (also good interview material)

- Xiaohongshu's hot list responds, but its `update_time` is often days stale; the source timestamp is stored as-is, never faked fresh.
- Bilibili creator feeds (ATIpiu, 脑洞视界) return 412 from a plain direct connection; the radar this project came from reaches them through a system proxy. This project ships no proxy config, so that source is documented as pending in `docs/SOURCES.md`, not faked.
- X, Product Hunt and WeChat hot lists need developer keys or have no legal public API; not connected, documented as such.
- One source failing never stops a run: the failed source keeps its previous snapshot and the failure is recorded in `refresh_log` and in the report header.

## Project layout

```
radar_pipeline/
  sources.py   # fetchers, one (rows, error) pair per source; no keys needed
  clean.py     # pure functions: normalize, de-duplicate, flag, parse ints
  store.py     # SQLite schema + per-source snapshot replace + refresh log
  analyze.py   # read-only queries + Markdown report builder
  run.py       # entry point: fetch → clean → store → log → report
tests/         # test_clean.py, test_sources.py, test_run.py (stdlib only)
docs/SOURCES.md
reports/latest.md   # generated by each run; refreshed daily by Actions
```

## Roadmap

- Trend history: keep each snapshot's ranks over time to show topics rising/falling.
- Swap SQLite for Postgres/DuckDB — only `store.py` needs to change.
- More no-key sources as they are verified (see `docs/SOURCES.md`).

## License

MIT — see [LICENSE](LICENSE).
