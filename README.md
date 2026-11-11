# 全网热点雷达 · 数据管道（hot-radar-pipeline）

把「全网热点与 AI 资讯雷达」的数据采集、清洗、入库、分析，做成一个能跑的 Python 项目。
数据源全部是已实测过的免注册、免 Key 公开接口（见 `docs/SOURCES.md`），不用花钱、不用注册。

## 数据怎么流

```
采集（sources.py） → 清洗（clean.py） → 入库 SQLite（store.py） → 分析出报告（analyze.py）
   UAPI 11 平台热榜        标题归一化、去重        hot_items / ai_items     跨平台热议、平台统计
   Hugging Face 趋势模型    跨平台同题打标          refresh_log（每源成败）  AI 模型趋势、最新论文
   Hacker News / GitHub     hot_value 转数字                         报告写到 reports/latest.md
   RSS（The Verge / OpenAI / IT之家 / 量子位）
```

## 快速开始

```bash
# 只需要 Python 3.10+，零第三方依赖
python -m radar_pipeline.run

# 只跑采集+入库，不出报告
python -m radar_pipeline.run --no-report

# 指定数据库和报告位置
python -m radar_pipeline.run --db data/radar.db --report reports/latest.md
```

跑完会打印每源拉到几条、失败是哪个源；报告在 `reports/latest.md`，数据库在 `data/radar.db`。

## 库表

| 表 | 内容 | 更新方式 |
| --- | --- | --- |
| `hot_items` | 各平台热榜：platform / rank / title / url / hot_value / source_updated_at / fetched_at | 每次按 source 全量替换，只留最新快照 |
| `ai_items` | AI 区：kind（model/paper/tech/oss/news）/ title / url / score / source / published_at | 同上，按 kind+source 替换 |
| `refresh_log` | 每次刷新每源的成功/失败与条数，只留最近 50 条 | 追加 |

## 清洗规则（clean.py）

- 标题归一化：去标点、去空白、全小写后做跨平台同题匹配；同一标题出现在 ≥2 个平台时打 `cross_platform=1`。
- 同一平台内按 `(platform, 归一化标题)` 去重，只留 rank 最小的一条。
- `hot_value` 转整数，转不了记 NULL，不丢整条。
- 缺标题或缺链接的行直接丢弃，并计入 `refresh_log` 的 dropped 数。

## 跑测试

```bash
python -m unittest discover -s tests -v
```

测试只测清洗与分析逻辑，不联网。

## 诚实说明（面试也能讲）

- 小红书热榜能返回，但它的 `update_time` 经常停在几天前，入库时原样保留源更新时间，不假装新鲜。
- B 站关注创作者（ATIpiu、脑洞视界）本机直连会被 B 站风控 412，雷达空间里是走系统代理才通的；本项目 v1 不含这路，只在 `docs/SOURCES.md` 里标为待接入，不编数据。
- X、Product Hunt、微信热榜需要注册开发者 Key，按「需要注册的再说」，v1 不接，文档里如实标注。
- 单个源失败不影响整次运行：失败源保留上次快照，`refresh_log` 里记失败原因。

## 下一步可以加的

- 定时任务（cron / GitHub Actions）每 2 小时跑一次，和雷达空间同节奏。
- 热度趋势表：把每次快照的 rank 存成历史，算话题升降。
- 换 Postgres / DuckDB，只改 `store.py` 一处。
