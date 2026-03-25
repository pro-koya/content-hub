"""
X (Twitter) Trending Collector
X API v2 でバズっている投稿を取得・分析する。

NOTE: search_recent_tweets は Free プランでは利用不可（Basic $100/month 以上が必要）。
Free プランの場合は API 呼び出しをスキップし、警告を表示する。
代替として RSS ベースのフォールバック（Nitter 互換 etc.）を提供する。
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta

import requests

from src.collectors.rss import Article

JST = timezone(timedelta(hours=9))

SEARCH_QUERIES = [
    "AI駆動開発",
    "個人開発",
    "スマート農業",
    "兼業農家",
    "フリーランス エンジニア",
]

ALTERNATIVE_RSS_SOURCES = [
    {
        "name": "Google News - AI開発バズ",
        "url": "https://news.google.com/rss/search?q=AI%E9%A7%86%E5%8B%95%E9%96%8B%E7%99%BA+site:x.com+OR+site:twitter.com&hl=ja&gl=JP&ceid=JP:ja",
    },
    {
        "name": "Google News - AI個人開発",
        "url": "https://news.google.com/rss/search?q=%E5%80%8B%E4%BA%BA%E9%96%8B%E7%99%BA+AI+%E3%83%90%E3%82%BA&hl=ja&gl=JP&ceid=JP:ja",
    },
]


def _create_client():
    """X API クライアントを作成。環境変数未設定の場合は None を返す。"""
    try:
        import tweepy
    except ImportError:
        print("  [WARN] tweepy がインストールされていません。")
        return None

    bearer = os.environ.get("X_BEARER_TOKEN", "")
    if bearer:
        return tweepy.Client(bearer_token=bearer)

    api_key = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    access_token = os.environ.get("X_ACCESS_TOKEN", "")
    access_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    if all([api_key, api_secret, access_token, access_secret]):
        return tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

    return None


def _fetch_via_api(
    queries: list[str],
    since_timestamp: int,
    limit: int,
) -> list[Article]:
    """X API v2 (Basic+ プラン) 経由で取得する。"""
    import tweepy

    client = _create_client()
    if client is None:
        return []

    all_articles: list[Article] = []

    for query in queries:
        search_query = f"{query} lang:ja -is:retweet"
        print(f"    Searching X API: {search_query}")
        try:
            response = client.search_recent_tweets(
                query=search_query,
                max_results=10,
                tweet_fields=["created_at", "public_metrics", "author_id", "text"],
                sort_order="relevancy",
            )

            if response is None or not response.data:
                continue

            for tweet in response.data:
                created_at = tweet.created_at
                ts = int(created_at.timestamp()) if created_at else int(time.time())

                if ts < since_timestamp:
                    continue

                metrics = tweet.public_metrics or {}
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                replies = metrics.get("reply_count", 0)

                engagement_info = f"❤️{likes} 🔄{retweets} 💬{replies}"
                tweet_url = f"https://x.com/i/status/{tweet.id}"

                all_articles.append(Article(
                    id=str(tweet.id),
                    title=f"{tweet.text[:80]}... [{engagement_info}]",
                    url=tweet_url,
                    content=tweet.text,
                    feed_title=f"X ({query})",
                    category="X_BUZZ",
                    published=ts,
                ))

        except tweepy.errors.Forbidden as e:
            print(f"  [WARN] X API 403 Forbidden: Free プランでは search_recent_tweets は利用できません。")
            print(f"         Basic プラン ($100/month) 以上にアップグレードするか、代替ソースを使用します。")
            return []
        except tweepy.errors.Unauthorized:
            print(f"  [WARN] X API 401 Unauthorized: 認証情報を確認してください。")
            return []
        except tweepy.errors.TooManyRequests:
            print("  [WARN] X API rate limit reached. Stopping.")
            break
        except Exception as e:
            print(f"  [WARN] X API error: {e}")

        time.sleep(1.0)

    return all_articles


def _fetch_via_google_rss(limit: int) -> list[Article]:
    """Google News RSS 経由で X/Twitter 関連のバズ記事を取得する（フォールバック）。"""
    from src.collectors.rss import fetch_feed

    all_articles: list[Article] = []

    for source in ALTERNATIVE_RSS_SOURCES:
        print(f"    Fetching X buzz (Google News RSS): {source['name']}")
        try:
            articles = fetch_feed(
                feed_url=source["url"],
                feed_name=source["name"],
                category="X_BUZZ",
                since_timestamp=0,
                limit=limit,
            )
            all_articles.extend(articles)
        except Exception as e:
            print(f"  [WARN] RSS fallback error: {e}")
        time.sleep(0.3)

    return all_articles


def fetch_trending_posts(
    queries: list[str] | None = None,
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """X API で指定クエリのバズ投稿を取得する。API 失敗時は RSS フォールバック。"""
    if queries is None:
        queries = SEARCH_QUERIES

    articles = _fetch_via_api(queries, since_timestamp, limit)

    if not articles:
        print("  [INFO] X API から記事を取得できませんでした。Google News RSS フォールバックを使用します。")
        articles = _fetch_via_google_rss(limit)

    seen_ids = set()
    unique = []
    for a in articles:
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            unique.append(a)

    unique.sort(key=lambda a: a.published, reverse=True)
    return unique[:limit]
