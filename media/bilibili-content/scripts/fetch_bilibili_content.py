#!/usr/bin/env python3
"""
Fetch Bilibili video metadata, attempt subtitle extraction, and optionally
fetch the original source article from the video description.

Usage:
    uv run python3 fetch_bilibili_content.py <url_or_bvid> [--fetch-article]

Output (JSON):
    {
        "bvid": "BV1XLgx6WEzm",
        "title": "用 Rust 重写整个世界?",
        "up": "沙漠在逃",
        "duration_sec": 485,
        "desc": "https://bitfieldconsulting.com/posts/rewrite-in-rust",
        "cid": 40234781268,
        "aid": 116970196305861,
        "subtitles": [],
        "source_article": "..."  // only if --fetch-article and URL found in desc
    }

No external dependencies — uses stdlib (urllib, json, re, html).
"""

import argparse
import json
import re
import sys
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def resolve_short_link(url):
    """Resolve b23.tv short link to full URL, extracting BV ID."""
    if "b23.tv/" in url:
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.geturl()
        return extract_bvid(final_url)
    return extract_bvid(url)


def extract_bvid(url_or_id):
    """Extract BV ID from URL or raw ID."""
    url_or_id = url_or_id.strip()
    match = re.search(r"(BV[a-zA-Z0-9]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id


def fetch_metadata(bvid):
    """Fetch video metadata via Bilibili web API."""
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    raw = fetch(api_url)
    data = json.loads(raw).get("data", {})
    return {
        "bvid": bvid,
        "title": data.get("title", ""),
        "up": data.get("owner", {}).get("name", ""),
        "duration_sec": data.get("duration", 0),
        "desc": data.get("desc", ""),
        "cid": data.get("cid", 0),
        "aid": data.get("aid", 0),
        "tname": data.get("tname", ""),
        "view": data.get("stat", {}).get("view", 0),
    }


def fetch_subtitles(cid, aid, bvid):
    """Attempt to fetch CC subtitle list. Returns empty list if none."""
    api_url = f"https://api.bilibili.com/x/player/v2?cid={cid}&aid={aid}"
    try:
        raw = fetch(api_url, timeout=10)
        data = json.loads(raw).get("data", {})
        subs = data.get("subtitle", {}).get("subtitles", [])
        return subs
    except Exception:
        return []


def extract_source_url(desc):
    """Extract the first article/blog/paper URL from video description."""
    if not desc:
        return None
    urls = re.findall(r"https?://[^\s]+", desc)
    # Prefer article/blog/paper URLs over social media
    skip_prefixes = ("t.bilibili.com", "weibo.com", "twitter.com", "x.com",
                     "b23.tv", "space.bilibili.com")
    for url in urls:
        if not any(url.startswith(f"https://{p}") for p in skip_prefixes):
            return url.rstrip("/")
    # Fall back to first URL if all are social
    return urls[0].rstrip("/") if urls else None


def fetch_article_text(url):
    """Fetch a URL and extract plain text (strip HTML)."""
    try:
        raw = fetch(url, timeout=20)
    except Exception as e:
        return f"[fetch error: {e}]"

    # Try <article> or <main> first
    body = re.search(r"<article[^>]*>(.*?)</article>", raw, re.DOTALL)
    if not body:
        body = re.search(r"<main[^>]*>(.*?)</main>", raw, re.DOTALL)
    text = body.group(1) if body else raw

    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "\n".join(lines[:500])  # cap at 500 lines


def main():
    parser = argparse.ArgumentParser(description="Fetch Bilibili video content")
    parser.add_argument("url", help="B站 URL or BV ID")
    parser.add_argument("--fetch-article", action="store_true",
                        help="Fetch original source article from description")
    args = parser.parse_args()

    bvid = resolve_short_link(args.url)
    if not bvid.startswith("BV"):
        print(json.dumps({"error": f"Could not extract BV ID from: {args.url}"}))
        sys.exit(1)

    meta = fetch_metadata(bvid)
    subs = fetch_subtitles(meta["cid"], meta["aid"], bvid)
    meta["subtitles"] = subs

    if args.fetch_article:
        source_url = extract_source_url(meta["desc"])
        if source_url:
            meta["source_url"] = source_url
            meta["source_article"] = fetch_article_text(source_url)
        else:
            meta["source_url"] = None

    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
