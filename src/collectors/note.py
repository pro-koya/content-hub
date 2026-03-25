"""
note Collector
note の RSS フィードと検索 API からトレンド記事を取得する。
note はRSSを公開しているため、まずRSSベースで取得する。
"""

from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from src.collectors.rss import Article, _HEADERS

NOTE_RSS_FEEDS = [
    {
        "name": "note テクノロジー",
        "url": "https://note.com/topic/technology/rss",
    },
    {
        "name": "note プログラミング",
        "url": "https://note.com/topic/programming/rss",
    },
    {
        "name": "note AI",
        "url": "https://note.com/topic/ai/rss",
    },
    {
        "name": "note 農業",
        "url": "https://note.com/topic/agriculture/rss",
    },
]

NOTE_SEARCH_KEYWORDS = [
    "AI駆動開発",
    "兼業農家",
    "フリーランス エンジニア 農業",
    "スマート農業",
]


def fetch_from_rss(
    since_timestamp: int,
    limit: int = 10,
) -> list[Article]:
    """note のトピック別 RSS からトレンド記事を取得する。"""
    from src.collectors.rss import fetch_feed

    all_articles: list[Article] = []

    for feed_info in NOTE_RSS_FEEDS:
        print(f"    Fetching note RSS: {feed_info['name']}")
        articles = fetch_feed(
            feed_url=feed_info["url"],
            feed_name=feed_info["name"],
            category="NOTE_TRENDING",
            since_timestamp=since_timestamp,
            limit=limit,
        )
        all_articles.extend(articles)
        time.sleep(0.3)

    seen_urls = set()
    unique = []
    for a in all_articles:
        if a.url not in seen_urls:
            seen_urls.add(a.url)
            unique.append(a)

    unique.sort(key=lambda a: a.published, reverse=True)
    return unique[:limit]


def fetch_by_search(
    keywords: list[str] | None = None,
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """note の検索ページから記事を取得する（軽量スクレイピング）。"""
    if keywords is None:
        keywords = NOTE_SEARCH_KEYWORDS

    all_articles: list[Article] = []

    for keyword in keywords:
        print(f"    Searching note: {keyword}")
        try:
            resp = requests.get(
                f"https://note.com/search",
                params={"q": keyword, "context": "note", "mode": "search"},
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"  [WARN] note search {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            note_cards = soup.select("a[href*='/n/']")

            for card in note_cards[:5]:
                url = card.get("href", "")
                if not url.startswith("https://"):
                    url = f"https://note.com{url}"
                title = card.get_text(strip=True)[:100]
                if not title or len(title) < 5:
                    continue

                all_articles.append(Article(
                    id=url,
                    title=title,
                    url=url,
                    content="",
                    feed_title=f"note ({keyword})",
                    category="NOTE_TRENDING",
                    published=0,
                ))

        except Exception as e:
            print(f"  [WARN] note search error: {e}")

        time.sleep(1.0)

    seen_urls = set()
    unique = []
    for a in all_articles:
        if a.url not in seen_urls:
            seen_urls.add(a.url)
            unique.append(a)

    return unique[:limit]


def fetch_note_articles(
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """RSS + 検索を統合して note の記事を取得する。"""
    rss_articles = fetch_from_rss(since_timestamp, limit)

    if len(rss_articles) < limit:
        remaining = limit - len(rss_articles)
        search_articles = fetch_by_search(limit=remaining, since_timestamp=since_timestamp)
        rss_articles.extend(search_articles)

    seen_urls = set()
    unique = []
    for a in rss_articles:
        if a.url not in seen_urls:
            seen_urls.add(a.url)
            unique.append(a)

    return unique[:limit]
