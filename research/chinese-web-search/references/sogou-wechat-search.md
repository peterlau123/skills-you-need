# Sogou WeChat Search — Session Findings

## Session context

User asked to find a Douyin article titled "从信息论看LLM：压缩即智能（一）香农熵" by searching the web. The task required trying ~10 different search engines/platforms before finding one that worked.

## Endpoints tested and results

| Endpoint | URL | Status | Result |
|----------|-----|--------|--------|
| Sogou WeChat | `weixin.sogou.com/weixin?type=2&query=...` | ✅ Works | Server-rendered HTML with article metadata |
| Bing RSS | `www.bing.com/search?format=rss&q=...` | ⚠️ Poor | Chinese queries tokenized to individual chars, returns irrelevant results |
| Bing HTML | `www.bing.com/search?q=...&ensearch=0` | ⚠️ Poor | Returns few/no real results, URLs behind `ck/a` redirects |
| Baidu | `www.baidu.com/s?wd=...` | ❌ Blocked | Returns CAPTCHA/security verification page |
| Sogou web | `www.sogou.com/web?query=...` | ❌ Blocked | Returns "risky plugin detected" page |
| Zhihu API | `zhihu.com/api/v4/search_v3` | ❌ Empty | Returns `{"HitLabels":null}` without auth |
| Zhihu web | `zhihu.com/search` | ❌ JS-only | 650 bytes, no server-side content |
| CSDN search | `so.csdn.net/so/search` | ❌ JS-only | Requires JS rendering |
| Juejin search | `so.juejin.cn/search` | ❌ JS-only | 713 bytes, no server-side content |
| Douyin | `v.douyin.com/...` | ❌ JS-only | Heavily obfuscated JS, zero Chinese text in source |
| Google | `google.com/search` | ❌ Unreachable | Connection fails entirely |
| DuckDuckGo | `html.duckduckgo.com/html/` | ❌ Unreachable | Connection fails entirely (0 bytes) |

## Effective query variations

The following queries all returned 10 results each from Sogou WeChat search:

1. `从信息论看LLM 压缩即智能 香农熵` — found articles about Shannon entropy + LLM
2. `压缩即智能 LLM` — found articles about "compression is intelligence"
3. `从信息论看LLM` — broader info-theory + LLM articles
4. `从信息论看 LLM 压缩即智能` — overlap with #1 but different results
5. `压缩即智能 香农熵 信息论` — found entropy-specific articles

## What the search returned

Each search returned 10 results. Across 5 searches (~50 total results, with some overlap), we gathered:

- **Titles**: e.g., "别争了!香农老婆,才是世界上第一个大语言模型", "压缩即理解,即抽象,即生成", "张俊林:GPT4等LLM模型具备类人智慧了吗?"
- **Snippets**: 150-300 char excerpts containing search terms, enough to synthesize the core topic
- **Sources**: WeChat public account names (e.g., 图灵人工智能, 将门创投, 深度学习自然语言处理, 李rumor)
- **Images**: `mmbiz.qpic.cn` URLs embedded in `sogoucdn.com` thumbnail links

## What was NOT obtainable

- Full article text (Sogou redirect links hit CAPTCHA when followed via curl)
- Original Douyin article content (fully JS-rendered, no server-side text)
- Direct WeChat article URLs (hidden behind Sogou's redirect/encoding)

## Key lesson

Start with Sogou WeChat search immediately for Chinese content queries. Do not waste 15+ tool calls trying Bing, Google, Baidu, Zhihu, CSDN, etc. — they are either blocked, JS-rendered, or return poor Chinese results from this host.
