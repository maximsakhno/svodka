#!/usr/bin/env python3
"""Собирает посты из Bluesky, сохраняет в raw/YYYY-MM-DD.md."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
import os

load_dotenv()

POSTS_PER_ACCOUNT = 50
POSTS_PER_FEED = 50


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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sources = load_sources()

    all_posts = collect_bluesky(sources)
    if not all_posts:
        print("Нет постов для сохранения — проверьте sources.yaml и credentials")
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path("raw") / f"{date_str}.md"
    out_path.parent.mkdir(exist_ok=True)

    header = (
        f"# Raw feed — {date_str}\n\n"
        f"Bluesky: {len(all_posts)} постов\n\n---\n\n"
    )
    out_path.write_text(header + "\n".join(all_posts), encoding="utf-8")
    print(f"Сохранено {len(all_posts)} постов → {out_path}")


if __name__ == "__main__":
    main()
