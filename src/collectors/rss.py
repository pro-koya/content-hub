"""
RSS/Atom Feed Collector
feedparser でフィードを直接取得する。サーバー不要。
"""

from __future__ import annotations

import time
from calendar import timegm
from dataclasses import dataclass

import feedparser
import requests
import yaml

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ContentHubBot/1.0; +https://github.com)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


@dataclass
class Article:
    id: str
    title: str
    url: str
    content: str
    feed_title: str
    category: str
    published: int
    is_starred: bool = False
    is_read: bool = False


def _parse_timestamp(entry) -> int:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return int(timegm(t))
    return int(time.time())


def _fetch_raw(url: str, timeout: int = 30) -> str | None:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"  [WARN] HTTP fetch failed: {url} ({e})")
    return None


def fetch_feed(
    feed_url: str,
    feed_name: str,
    category: str,
    since_timestamp: int,
    limit: int = 50,
) -> list[Article]:
    raw = _fetch_raw(feed_url)
    if raw is None:
        return []

    try:
        d = feedparser.parse(raw)
    except Exception as e:
        print(f"  [WARN] Feed parse failed: {feed_url} ({e})")
        return []

    if d.bozo and not d.entries:
        print(f"  [WARN] Feed parse error: {feed_url} ({d.bozo_exception})")
        return []

    feed_title = d.feed.get("title", feed_name) if d.feed else feed_name
    articles = []

    for entry in d.entries:
        ts = _parse_timestamp(entry)
        if ts < since_timestamp:
            continue

        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary or ""
        elif hasattr(entry, "description"):
            content = entry.description or ""

        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "(No Title)") or "(No Title)"
        entry_id = getattr(entry, "id", url) or url

        articles.append(Article(
            id=entry_id,
            title=title,
            url=url,
            content=content,
            feed_title=feed_title,
            category=category,
            published=ts,
        ))

    articles.sort(key=lambda a: a.published, reverse=True)
    return articles[:limit]


def fetch_category_feeds(
    feeds_config_path: str,
    category: str,
    since_timestamp: int,
    limit: int = 50,
) -> list[Article]:
    with open(feeds_config_path) as f:
        config = yaml.safe_load(f) or {}

    cat_config = config.get("categories", {}).get(category)
    if not cat_config:
        return []

    all_articles: list[Article] = []
    for feed in cat_config.get("feeds", []):
        feed_url = feed["url"]
        feed_name = feed.get("name", feed_url)
        print(f"    Fetching: {feed_name}")
        articles = fetch_feed(feed_url, feed_name, category, since_timestamp, limit)
        all_articles.extend(articles)
        time.sleep(0.3)

    all_articles.sort(key=lambda a: a.published, reverse=True)
    return all_articles[:limit]
