"""
X (Twitter) Trending Collector
X API v2 でバズっている投稿を取得・分析する。
Free tier: 読み取り 10,000 tweets/month。
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone, timedelta

import tweepy

from src.collectors.rss import Article

JST = timezone(timedelta(hours=9))

SEARCH_QUERIES = [
    "AI駆動開発 min_faves:10",
    "個人開発 min_faves:20",
    "スマート農業 min_faves:5",
    "兼業農家 min_faves:5",
    "フリーランス エンジニア min_faves:10",
    "#AI開発 min_faves:5",
]


def _create_client() -> tweepy.Client | None:
    """X API クライアントを作成。環境変数未設定の場合は None を返す。"""
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


def fetch_trending_posts(
    queries: list[str] | None = None,
    since_timestamp: int = 0,
    limit: int = 10,
) -> list[Article]:
    """X API で指定クエリのバズ投稿を取得する。"""
    client = _create_client()
    if client is None:
        print("  [WARN] X API credentials not configured. Skipping X trending.")
        return []

    if queries is None:
        queries = SEARCH_QUERIES

    all_articles: list[Article] = []

    for query in queries:
        print(f"    Searching X: {query}")
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=10,
                tweet_fields=["created_at", "public_metrics", "author_id", "text"],
                sort_order="relevancy",
            )

            if response is None or not response.data:
                continue

            for tweet in response.data:
                created_at = tweet.created_at
                if created_at:
                    ts = int(created_at.timestamp())
                else:
                    ts = int(time.time())

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
                    title=f"{tweet.text[:60]}... [{engagement_info}]",
                    url=tweet_url,
                    content=tweet.text,
                    feed_title=f"X ({query.split(' min_faves')[0]})",
                    category="X_BUZZ",
                    published=ts,
                ))

        except tweepy.TooManyRequests:
            print("  [WARN] X API rate limit reached. Stopping.")
            break
        except Exception as e:
            print(f"  [WARN] X API error: {e}")

        time.sleep(1.0)

    seen_ids = set()
    unique = []
    for a in all_articles:
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            unique.append(a)

    unique.sort(key=lambda a: a.published, reverse=True)
    return unique[:limit]
