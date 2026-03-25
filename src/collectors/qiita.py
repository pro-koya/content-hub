"""
Qiita Collector
Qiita API v2 でトレンド記事・タグ別記事を取得する。
API キー不要（レート制限: 認証なしで 60 req/hour）。
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import requests

from src.collectors.rss import Article

_BASE_URL = "https://qiita.com/api/v2"
_HEADERS = {
    "User-Agent": "ContentHubBot/1.0",
    "Accept": "application/json",
}

QIITA_TAGS = [
    "AI",
    "機械学習",
    "LLM",
    "ChatGPT",
    "Python",
    "個人開発",
    "農業",
    "スマート農業",
]


def _api_get(endpoint: str, params: dict | None = None) -> list[dict]:
    headers = dict(_HEADERS)
    api_key = os.environ.get("QIITA_ACCESS_TOKEN", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(
            f"{_BASE_URL}/{endpoint}",
            params=params or {},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        print(f"  [WARN] Qiita API {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [WARN] Qiita API error: {e}")
    return []


def _parse_timestamp(created_at: str) -> int:
    if not created_at:
        return 0
    try:
        return int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def fetch_trending(
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """Qiita のストック数上位の新着記事を取得する。"""
    articles: list[Article] = []

    lookback_date = datetime.now(timezone.utc) - timedelta(days=7)
    date_str = lookback_date.strftime("%Y-%m-%d")

    params = {
        "page": "1",
        "per_page": str(min(limit * 3, 100)),
        "query": f"stocks:>3 created:>{date_str}",
    }
    print(f"    Fetching Qiita trending (stocks:>3, since {date_str})")
    items = _api_get("items", params)

    for item in items:
        ts = _parse_timestamp(item.get("created_at", ""))
        tags = [t.get("name", "") for t in item.get("tags", [])]

        articles.append(Article(
            id=item.get("id", ""),
            title=item.get("title", "(No Title)"),
            url=item.get("url", ""),
            content=item.get("rendered_body", item.get("body", ""))[:3000],
            feed_title=f"Qiita (@{item.get('user', {}).get('id', 'unknown')}) [{', '.join(tags[:3])}]",
            category="QIITA_TRENDING",
            published=ts,
        ))

    articles.sort(key=lambda a: a.published, reverse=True)
    return articles[:limit]


def fetch_by_tags(
    tags: list[str] | None = None,
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """指定タグの最新記事を取得する。"""
    if tags is None:
        tags = QIITA_TAGS

    all_articles: list[Article] = []
    per_tag_limit = max(3, limit // len(tags)) if tags else limit

    for tag in tags:
        print(f"    Fetching Qiita tag: {tag}")
        params = {
            "page": "1",
            "per_page": str(min(per_tag_limit * 2, 20)),
            "query": f"tag:{tag}",
        }
        items = _api_get("items", params)

        for item in items:
            ts = _parse_timestamp(item.get("created_at", ""))
            item_tags = [t.get("name", "") for t in item.get("tags", [])]

            all_articles.append(Article(
                id=item.get("id", ""),
                title=item.get("title", "(No Title)"),
                url=item.get("url", ""),
                content=item.get("rendered_body", item.get("body", ""))[:3000],
                feed_title=f"Qiita ({tag}) [{', '.join(item_tags[:3])}]",
                category="QIITA_TRENDING",
                published=ts,
            ))

        time.sleep(0.5)

    seen_ids = set()
    unique = []
    for a in all_articles:
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            unique.append(a)

    unique.sort(key=lambda a: a.published, reverse=True)
    return unique[:limit]
