# 数据源清单（全部已实测，免注册免 Key）

实测记录来自雷达空间的 DATA-PLAN（`~/workspace/ts-spaces/quan-wang-re-dian-yu-ai-zi-xun-lei-da/DATA-PLAN.md`），
本项目只复用其中不依赖系统代理的那部分。

## 已接入

| 源 | 接口 | 取数 |
| --- | --- | --- |
| UAPI 热榜聚合 | `https://uapis.cn/api/v1/misc/hotboard?type=<平台>` | 11 平台（微博/知乎/百度/B站/抖音/头条/快手/小红书/澎湃/36氪/IT之家），各前 30 |
| Hugging Face | `https://huggingface.co/api/models?sort=trendingScore…`、`…/api/daily_papers` | 趋势模型 15、每日论文 10 |
| Hacker News | `https://hacker-news.firebaseio.com/v0/topstories.json` + item 接口 | 前 30 取详情，留 12 |
| GitHub Search | `https://api.github.com/search/repositories?q=created:>近7天+stars:>50` | AI 相关新仓库 10（未认证限额 60 次/小时，一次运行只调 1 次） |
| RSS | The Verge AI、OpenAI 官方、IT之家、量子位 | 各前 10 |
| arXiv | `https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL…` | 最新 8 篇 |

## 待接入（v1 不接，原因如实写）

- **B 站关注创作者（ATIpiu、脑洞视界）**：空间投稿接口实测可用，但本机直连出口会被 B 站风控 412，
  雷达空间是走系统代理才通的。本项目不内置代理配置，先不接，不编数据。
- **X / Product Hunt / 微信热榜**：需注册开发者 Key，或无合法公开接口，按「需要注册的再说」，不接。
- **科特viktor**：B 站无同名账号、抖音无公开接口，无法接入，不伪造。

## 已弃用的源（别再接）

- api-hot.imsyy.top / DailyHotApi：实测返回空或 500。
- vvhan / tenapi / oioweb 热榜 API：实测空或 502。
- RSSHub 公共实例：官方明确提示将限制访问。
