---
name: bilibili-content
description: "Use when user shares a B站 video link for summary."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [bilibili, b站, video, summary, chinese-media]
---

# Bilibili (B站) Video Content Analysis

Use when the user shares a B站 video link (`https://b23.tv/<short>` or
`https://www.bilibili.com/video/BV<id>`) and asks to summarize, analyze, or extract
content from it. Reply in Chinese — the user works in a Feishu workspace.

## Short link resolution

B站 short links (`b23.tv`) return a 301 redirect to the full bilibili.com URL:

```bash
curl -sI --max-time 15 "https://b23.tv/<short>" | grep -i location
# → location: https://www.bilibili.com/video/BV1XLgx6WEzm?...
```

Extract the `BV<id>` from the redirect URL. Do NOT try to `curl -sL` the short link
body — it returns compressed binary, not HTML.

## Fetch video metadata via API

```bash
BVID="BV1XLgx6WEzm"
curl -s --max-time 15 "https://api.bilibili.com/x/web-interface/view?bvid=$BVID" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import json, sys
d = json.load(sys.stdin).get('data', {})
print('标题:', d.get('title', ''))
print('UP主:', d.get('owner', {}).get('name', ''))
print('时长:', d.get('duration', ''), '秒')
print('播放:', d.get('stat', {}).get('view', ''))
print('简介:', d.get('desc', '')[:500])
"
```

- The `desc` field often contains a URL to the original article/source the video is based on.
  This is the **primary fallback** when no CC subtitles are available.
- `cid` is needed for subtitle API: extract from `data.cid`.

## CC subtitle check

```bash
CID=<from metadata above>
curl -s --max-time 10 \
  "https://api.bilibili.com/x/player/v2?cid=$CID&bvid=$BVID" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import json, sys
d = json.load(sys.stdin).get('data', {})
sub = d.get('subtitle', {})
print('字幕列表:', json.dumps(sub, ensure_ascii=False)[:300])
"
```

- `subtitles: []` means no CC subtitles — most B站 videos don't have them.
- If subtitles exist, fetch from the subtitle URL in the response (`.json` format with
  `body[].content` text segments).

## Fallback strategy (when no subtitles)

1. **Check `desc` for a source URL** — many B站 tech videos are based on blog posts or
   articles. Fetch the referenced article and extract its full text. This is the most
   reliable path for tech content.
2. **Search for the video title + UP主 name** on the web to find related written content.
3. **Ask the user** to provide context or key points if no source is found.

### Extracting article text from a URL

```bash
curl -sL --max-time 20 -H "User-Agent: Mozilla/5.0" "<article_url>" | python3 -c "
import sys, re, html
t = sys.stdin.read()
body = re.search(r'<article[^>]*>(.*?)</article>', t, re.S) or \
       re.search(r'<main[^>]*>(.*?)</main>', t, re.S)
if not body:
    print('未找到正文，页面长度:', len(t)); sys.exit()
text = body.group(1)
text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.S)
text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(text)
lines = [l.strip() for l in text.split('\n') if l.strip()]
print('\n'.join(lines))
"
```

## User's preferred summary structure

When summarizing video/article content, use the **四段式** structure (declared 2026-08-07):

1. **是什么？** (What) — define the concept/project/technology
2. **为什么？** (Why) — why it matters, pain points, motivation
3. **怎样做？** (How) — approach, technical details, implementation
4. **什么样的结果？** (What results) — outcomes, data, impact

Apply **少即是多** (less is more): use tables and bullet points, not prose paragraphs.
This mirrors the user's general 3W1H work framework (What/Why/When/How) with a
results-oriented twist.

## Saving to wiki

If the user asks to save the summary to their wiki, follow the `ai-infra-wiki` skill
for vault path, note conventions, and git workflow. The user's ai-infra-wiki is at
`/data/lx/ai-engineer/ai-infra-wiki/`. Filing location depends on content type:

- **Open-source software blog posts** (migration strategies, language ecosystem debates,
  engineering culture about open-source projects) → `Opensources/` alongside existing
  source-code-analysis notes.
- **Vendor/infra deep-dives** (Anthropic, NVIDIA, vLLM) → under the matching hub
  (`AI-Cluster/` or `Agent/`) per the ai-infra-wiki skill.
- **Other topics** → check existing dirs via `search_files(target="files", pattern="*.md")`
  and follow the taxonomy.

The user explicitly called this out (2026-08-07): if the blog is *about* an open-source
project or ecosystem topic, it belongs in `Opensources/`, not under `AI-Cluster/`.

## Pitfalls

- `curl -sL` on `b23.tv` returns compressed binary (gzip), not readable HTML. Always
  use `-sI` (headers only) to get the redirect location.
- Most B站 videos have **no CC subtitles** (`subtitles: []`). Don't retry or loop —
  fall through to the desc/article fallback immediately.
- The bilibili API (`api.bilibili.com`) is accessible from this machine without auth
  for public video metadata. No API key needed.
- Some video descriptions are empty or contain only hashtags — the article URL fallback
  won't work in that case. Ask the user for context.
- `api.bilibili.com` may rate-limit if called too frequently. Add `--max-time 15` and
  don't batch more than a few requests.
- When fetching the article from `desc`, some sites (e.g. bitfieldconsulting.com) don't
  use `<article>` or `<main>` tags — the standard regex won't match. If the first extraction
  returns "未找到正文", try broader patterns: `<div class="*content*">`, `<body>`, or simply
  strip all HTML tags from the full page and filter for readable text. Always fetch at least
  `head -200` and `tail -80` to check both ends of a long article.
