"""
Qiita Collector
Qiita API v2 でトレンド記事・タグ別記事を取得する。
API キー不要（レート制限: 認証なしで 60 req/hour）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

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


def _api_get(endpoint: str, params: dict | None = None, api_key: str = "") -> list[dict]:
    headers = dict(_HEADERS)
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
            return resp.json()
        print(f"  [WARN] Qiita API {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [WARN] Qiita API error: {e}")
    return []


def fetch_trending(
    since_timestamp: int,
    limit: int = 10,
    api_key: str = "",
) -> list[Article]:
    """Qiita のストック数上位の記事を取得する。"""
    articles: list[Article] = []

    params = {
        "page": "1",
        "per_page": str(min(limit * 2, 100)),
        "query": "stocks:>5",
    }
    items = _api_get("items", params, api_key)

    for item in items:
        created_at = item.get("created_at", "")
        try:
            from datetime import datetime
            ts = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
        except (ValueError, AttributeError):
            ts = 0

        if ts < since_timestamp:
            continue

        tags = [t.get("name", "") for t in item.get("tags", [])]
        tag_str = ", ".join(tags[:3])

        articles.append(Article(
            id=item.get("id", ""),
            title=item.get("title", "(No Title)"),
            url=item.get("url", ""),
            content=item.get("rendered_body", item.get("body", ""))[:2000],
            feed_title=f"Qiita (@{item.get('user', {}).get('id', 'unknown')})",
            category="QIITA_TRENDING",
            published=ts,
        ))

    articles.sort(key=lambda a: a.published, reverse=True)
    return articles[:limit]


def fetch_by_tags(
    tags: list[str] | None = None,
    since_timestamp: int = 0,
    limit: int = 10,
    api_key: str = "",
) -> list[Article]:
    """指定タグの記事を取得する。"""
    if tags is None:
        tags = QIITA_TAGS

    all_articles: list[Article] = []
    per_tag_limit = max(3, limit // len(tags)) if tags else limit

    for tag in tags:
        print(f"    Fetching Qiita tag: {tag}")
        params = {
            "page": "1",
            "per_page": str(min(per_tag_limit * 2, 20)),
            "query": f"tag:{tag} stocks:>3",
        }
        items = _api_get("items", params, api_key)

        for item in items:
            created_at = item.get("created_at", "")
            try:
                from datetime import datetime
                ts = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
            except (ValueError, AttributeError):
                ts = 0

            if ts < since_timestamp:
                continue

            all_articles.append(Article(
                id=item.get("id", ""),
                title=item.get("title", "(No Title)"),
                url=item.get("url", ""),
                content=item.get("rendered_body", item.get("body", ""))[:2000],
                feed_title=f"Qiita ({tag})",
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
