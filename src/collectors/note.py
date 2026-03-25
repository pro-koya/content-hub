"""
note Collector
note API v3 を使ってトレンド・検索記事を取得する。
"""

from __future__ import annotations

import time

import requests

from src.collectors.rss import Article

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

NOTE_SEARCH_KEYWORDS = [
    "AI駆動開発",
    "LLM 開発",
    "個人開発 AI",
    "兼業農家",
    "スマート農業",
    "フリーランス エンジニア",
    "AI エンジニアリング",
]


def _search_notes(query: str, size: int = 10) -> list[Article]:
    """note API v3 で記事を検索する。"""
    articles: list[Article] = []

    try:
        resp = requests.get(
            "https://note.com/api/v3/searches",
            params={"q": query, "context": "note", "size": str(min(size, 20))},
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  [WARN] note API {resp.status_code} for '{query}'")
            return []

        data = resp.json()
        contents = data.get("data", {}).get("notes", {}).get("contents", [])

        for item in contents:
            user = item.get("user", {})
            urlname = user.get("urlname", "")
            key = item.get("key", "")
            name = item.get("name", "(No Title)")
            like_count = item.get("like_count", 0)

            if not urlname or not key:
                continue

            note_url = f"https://note.com/{urlname}/n/{key}"
            body = item.get("body", "") or item.get("description", "") or ""

            publish_at = item.get("publish_at", "")
            ts = 0
            if publish_at:
                try:
                    from datetime import datetime
                    ts = int(datetime.fromisoformat(publish_at).timestamp())
                except (ValueError, AttributeError):
                    ts = 0

            articles.append(Article(
                id=str(item.get("id", key)),
                title=name,
                url=note_url,
                content=body[:3000],
                feed_title=f"note ({query}) [♡{like_count}]",
                category="NOTE_TRENDING",
                published=ts,
            ))

    except Exception as e:
        print(f"  [WARN] note API error for '{query}': {e}")

    return articles


def fetch_note_articles(
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """複数キーワードで検索し、note の記事を取得する。"""
    all_articles: list[Article] = []

    per_keyword = max(3, limit // len(NOTE_SEARCH_KEYWORDS)) if NOTE_SEARCH_KEYWORDS else limit

    for keyword in NOTE_SEARCH_KEYWORDS:
        print(f"    Fetching note: {keyword}")
        arts = _search_notes(keyword, size=per_keyword)
        all_articles.extend(arts)
        time.sleep(0.5)

    seen_ids = set()
    unique = []
    for a in all_articles:
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            unique.append(a)

    unique.sort(key=lambda a: a.published, reverse=True)
    return unique[:limit]
