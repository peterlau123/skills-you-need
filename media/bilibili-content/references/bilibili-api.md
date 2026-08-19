# Bilibili API Reference

All endpoints are public (no auth needed for public videos). Add `User-Agent` header.

## 1. Short link resolution

`b23.tv/<code>` → 301 redirect to `www.bilibili.com/video/BV<id>?...`

```bash
# Method 1: headers only (recommended in existing skill)
curl -sI --max-time 15 "https://b23.tv/9SjCrKk" | grep -i location

# Method 2: effective URL (used in 2026-08-07 session, also works)
curl -sL -o /dev/null -w "%{url_effective}" "https://b23.tv/9SjCrKk"
```

Extract BV ID: `echo "$URL" | grep -oP 'BV[a-zA-Z0-9]+'`

## 2. Video metadata

**Endpoint**: `GET https://api.bilibili.com/x/web-interface/view`

**Params** (one of): `bvid=BVxxxx` or `aid=NNNN`

**Response** (key fields):
```json
{
  "code": 0,
  "data": {
    "title": "用 Rust 重写整个世界?",
    "desc": "https://bitfieldconsulting.com/posts/rewrite-in-rust",
    "duration": 485,
    "cid": 40234781268,
    "aid": 116970196305861,
    "owner": { "name": "沙漠在逃", "mid": 52374219 },
    "stat": { "view": 12345, "like": 678, "coin": 90, "share": 12 },
    "tname": "科技",
    "pubdate": 1786081102
  }
}
```

**Critical field**: `desc` — frequently contains the source article URL.
**Derived field**: `cid` — needed for subtitle API.

## 3. CC subtitles

**Endpoint**: `GET https://api.bilibili.com/x/player/v2`

**Params**: `cid=<CID>&aid=<AID>` or `cid=<CID>&bvid=<BVID>`

**Response** (subtitle section):
```json
{
  "data": {
    "subtitle": {
      "subtitles": [],
      "lan": "",
      "lan_doc": ""
    }
  }
}
```

- `subtitles: []` = no subtitles (most common for tech videos)
- If non-empty: each entry has `subtitle_url` → fetch JSON with `body[].content`

## 4. URL format reference

| Format | Example |
|---|---|
| Short link | `https://b23.tv/9SjCrKk` |
| Desktop | `https://www.bilibili.com/video/BV1XLgx6WEzm` |
| Mobile | `https://m.bilibili.com/video/BV1XLgx6WEzm` |
| Multi-part | `https://www.bilibili.com/video/BV1XLgx6WEzm/?p=2` |
| Raw BV ID | `BV1XLgx6WEzm` |

BV ID format: `BV` + 10 alphanumeric characters.

## 5. Rate limiting

- No documented rate limit for public metadata endpoints
- `--max-time 15` per request is sufficient
- Avoid batch-calling more than a few videos in rapid succession
