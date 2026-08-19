---
name: chinese-web-search
description: >-
  Search Chinese web content via Sogou WeChat search.
---

# Chinese Web Search

## When to use

- User asks to search for Chinese-language web content, articles, or news
- Searching for content published on WeChat (微信公众号), Douyin (抖音), Zhihu (知乎), CSDN, or other Chinese platforms
- Western search engines (Google, Bing) return poor or irrelevant results for Chinese queries
- User provides a Chinese article title and asks you to find its content or related articles

## Primary technique: Sogou WeChat search

Sogou WeChat search (`weixin.sogou.com`) is the most reliable curl-accessible endpoint for Chinese content. It searches WeChat public account articles specifically.

### Search URL pattern

```
https://weixin.sogou.com/weixin?type=2&query=<url-encoded-query>
```

- `type=2` searches articles (use `type=1` for accounts)
- Returns server-rendered HTML (no JS required for search results)
- Use a desktop browser User-Agent header

### Parsing results

The HTML contains `<li>` items inside `<ul class="news-list">`. Each result has:

| Field | HTML selector | Notes |
|-------|--------------|-------|
| Title | `<h3><a href="/link?url=...">title</a></h3>` | Search terms highlighted with `<!--red_beg-->`/`<!--red_end-->` comments |
| Snippet | `<p class="txt-info">snippet</p>` | ~150-300 chars, search terms highlighted same way |
| Source | `<span class="all-time-y2">account name</span>` | WeChat public account name |
| Thumbnail | `<img src="//img01.sogoucdn.com/...">` | Image URL encodes `mmbiz.qpic.cn` path |

### Regex for batch extraction (Python)

```python
import re

items = re.findall(
    r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>.*?</h3>.*?'
    r'<p class="txt-info"[^>]*>(.*?)</p>.*?'
    r'<span class="all-time-y2">(.*?)</span>',
    html, re.DOTALL
)
for title, snippet, source in items:
    # Strip highlight comments and tags
    title = re.sub(r'<[^>]+>|<!--red_beg-->|<!--red_end-->', '', title).strip()
    snippet = re.sub(r'<[^>]+>|<!--red_beg-->|<!--red_end-->', '', snippet).strip()
    source = re.sub(r'<[^>]+>', '', source).strip()
```

### Search strategy

1. Start with the full article title or key phrase
2. If no exact match, try progressively shorter keyword combinations
3. Run 3-5 query variations to maximize coverage — different keyword combos surface different articles
4. Extract all results across searches, deduplicate by title

## Pitfalls

- **Article links are Sogou redirects** (`/link?url=...`) that lead to a CAPTCHA/anti-spider page when followed via curl. You get search result metadata (title + snippet + source) but NOT full article text.
- **Highlight comments**: Sogou wraps matched search terms in `<!--red_beg-->`/`<!--red_end-->` HTML comments inside `<em>` tags. Strip these during parsing.
- **Query encoding**: Use `urllib.parse.quote()` for proper URL encoding of Chinese characters.
- **Rate limiting**: Sogou may redirect to homepage if too many requests are made quickly. Space out requests.
- **JS-rendered platforms**: Zhihu, CSDN, Juejin, and Douyin all return JS-rendered pages with no server-side content when accessed via curl. Use Sogou WeChat search as the entry point instead.
- **Bing RSS + Chinese**: Bing's RSS format (`format=rss`) does not handle Chinese queries well — it tokenizes on individual characters and returns irrelevant results. If using Bing for Chinese content, use the HTML endpoint and parse `b_algo` sections.
- **Google/DuckDuckGo**: May be completely unreachable from this host (connection failures). Do not waste tool calls retrying.

## What you can deliver

- Article titles, snippets (~150-300 chars), and source account names
- Identification of relevant articles across multiple searches
- Synthesized content summaries based on snippets from multiple related articles
- You CANNOT deliver full article text — tell the user to access articles directly via browser if they need complete content

## See also

- `references/sogou-wechat-search.md` — detailed session findings, query variations, and content extraction examples
