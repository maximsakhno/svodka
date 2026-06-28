#!/usr/bin/env python3
"""Собирает посты из Bluesky, сохраняет в raw/YYYY-MM-DD.md."""

import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
import os

load_dotenv()

POSTS_PER_ACCOUNT = 50
POSTS_PER_FEED = 50
RSS_ITEMS_PER_FEED = 20
RSS_SUMMARY_MAX_LEN = 500


def load_sources() -> dict:
    path = Path("sources.yaml")
    if not path.exists():
        sys.exit("sources.yaml не найден")
    with open(path) as f:
        return yaml.safe_load(f) or {}


# ── Bluesky ──────────────────────────────────────────────────────────────────

def collect_bluesky(sources: dict) -> list[str]:
    from atproto import Client

    handle = os.environ.get("BLUESKY_HANDLE")
    password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not password:
        print("[WARN] BLUESKY_HANDLE / BLUESKY_APP_PASSWORD не заданы, пропускаю Bluesky", file=sys.stderr)
        return []

    client = Client()
    client.login(handle, password)

    posts: list[str] = []
    seen: set[str] = set()

    for acc in sources.get("accounts") or []:
        acc = acc.strip()
        if not acc:
            continue
        try:
            feed = client.get_author_feed(actor=acc, limit=POSTS_PER_ACCOUNT)
            for item in feed.feed:
                uri = item.post.uri
                if uri in seen:
                    continue
                seen.add(uri)
                posts.append(_format_bsky_post(item))
        except Exception as e:
            print(f"[WARN] Bluesky @{acc}: {e}", file=sys.stderr)

    for feed_uri in sources.get("feeds") or []:
        feed_uri = feed_uri.strip()
        if not feed_uri:
            continue
        try:
            feed = client.app.bsky.feed.get_feed({"feed": feed_uri, "limit": POSTS_PER_FEED})
            for item in feed.feed:
                uri = item.post.uri
                if uri in seen:
                    continue
                seen.add(uri)
                posts.append(_format_bsky_post(item, source=feed_uri))
        except Exception as e:
            print(f"[WARN] Bluesky feed {feed_uri}: {e}", file=sys.stderr)

    return posts


def _format_bsky_post(post, source: str | None = None) -> str:
    record = post.post.record if hasattr(post, "post") else post.record
    author = post.post.author if hasattr(post, "post") else post.author
    uri = post.post.uri if hasattr(post, "post") else post.uri

    handle = author.handle
    text = getattr(record, "text", "").strip()
    created_at = getattr(record, "created_at", "")
    rkey = uri.split("/")[-1]
    url = f"https://bsky.app/profile/{handle}/post/{rkey}"
    source_label = source or f"@{handle}"

    return "\n".join([
        f"### [Bluesky] @{handle}",
        f"*Источник: {source_label}* | *{created_at}*",
        "",
        text,
        "",
        f"[Открыть]({url})",
        "",
        "---",
        "",
    ])


# ── RSS ───────────────────────────────────────────────────────────────────────

def collect_rss(sources: dict) -> list[str]:
    import feedparser

    urls = sources.get("rss_feeds") or []
    if not urls:
        return []

    items: list[str] = []
    seen: set[str] = set()

    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            source_title = feed.feed.get("title") or url
            for entry in feed.entries[:RSS_ITEMS_PER_FEED]:
                link = entry.get("link", "")
                if link in seen:
                    continue
                seen.add(link)
                items.append(_format_rss_entry(entry, source_title))
        except Exception as e:
            print(f"[WARN] RSS {url}: {e}", file=sys.stderr)

    return items


def _format_rss_entry(entry, source_title: str) -> str:
    title = (entry.get("title") or "Без заголовка").strip()
    link = entry.get("link") or ""
    published = entry.get("published") or entry.get("updated") or ""

    raw_summary = entry.get("summary") or ""
    clean = re.sub(r"<[^>]+>", "", raw_summary)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > RSS_SUMMARY_MAX_LEN:
        clean = clean[:RSS_SUMMARY_MAX_LEN].rstrip() + "…"

    return "\n".join([
        f"### [RSS] {title}",
        f"*Источник: {source_title}* | *{published}*",
        "",
        clean,
        "",
        f"[Открыть]({link})",
        "",
        "---",
        "",
    ])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sources = load_sources()

    bluesky_posts = collect_bluesky(sources)
    rss_items = collect_rss(sources)
    all_posts = bluesky_posts + rss_items

    if not all_posts:
        print("Нет постов для сохранения — проверьте sources.yaml и credentials")
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path("raw") / f"{date_str}.md"
    out_path.parent.mkdir(exist_ok=True)

    header = (
        f"# Raw feed — {date_str}\n\n"
        f"Bluesky: {len(bluesky_posts)} постов | RSS: {len(rss_items)} записей\n\n---\n\n"
    )
    out_path.write_text(header + "\n".join(all_posts), encoding="utf-8")
    print(f"Сохранено {len(all_posts)} записей → {out_path}")


if __name__ == "__main__":
    main()
