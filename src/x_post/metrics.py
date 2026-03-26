"""投稿済みツイートのメトリクスを取得し、data/post_metrics.json に保存する."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import tweepy

ROOT = Path(__file__).resolve().parent.parent.parent


def _create_x_client() -> tweepy.Client:
    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: 以下の環境変数が未設定です: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def load_posted_tweets() -> list[dict]:
    path = ROOT / "data" / "posted_tweets.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def fetch_metrics(client: tweepy.Client, tweet_ids: list[str]) -> dict[str, dict]:
    if not tweet_ids:
        return {}
    result: dict[str, dict] = {}
    for i in range(0, len(tweet_ids), 100):
        chunk = tweet_ids[i : i + 100]
        try:
            response = client.get_tweets(
                ids=chunk,
                tweet_fields=["public_metrics", "text"],
            )
        except Exception as e:
            print(f"WARNING: メトリクス取得でエラー: {e}", file=sys.stderr)
            continue
        if response is None or not getattr(response, "data", None):
            continue
        for tweet in response.data:
            mid = str(tweet.id)
            metrics = getattr(tweet, "public_metrics", None) or {}
            text = getattr(tweet, "text", None) or ""
            result[mid] = {
                "like_count": metrics.get("like_count", 0),
                "retweet_count": metrics.get("retweet_count", 0),
                "reply_count": metrics.get("reply_count", 0),
                "quote_count": metrics.get("quote_count", 0),
                "text": text,
            }
    return result


def run_fetch_metrics() -> None:
    posted = load_posted_tweets()
    if not posted:
        print("data/posted_tweets.json に投稿履歴がありません。スキップします。")
        return

    ids = [p["tweet_id"] for p in posted if p.get("tweet_id")]
    if not ids:
        print("有効な tweet_id がありません。")
        return

    client = _create_x_client()
    metrics_by_id = fetch_metrics(client, ids)

    posts_with_metrics: list[dict] = []
    for p in posted:
        tid = p.get("tweet_id")
        if not tid:
            continue
        m = metrics_by_id.get(tid) or {}
        like_count = int(m.get("like_count", 0) or p.get("like_count", 0))
        retweet_count = int(m.get("retweet_count", 0) or p.get("retweet_count", 0))
        reply_count = int(m.get("reply_count", 0) or p.get("reply_count", 0))
        text = (m.get("text") or p.get("text") or "").strip()
        engagement_score = like_count + retweet_count * 2 + reply_count
        posts_with_metrics.append({
            "tweet_id": tid,
            "date": p.get("date", ""),
            "text": text,
            "archetype": p.get("archetype", ""),
            "project": p.get("project", "liftly"),
            "hook_style": p.get("hook_style", ""),
            "tone": p.get("tone", ""),
            "cta_type": p.get("cta_type", ""),
            "posting_window": p.get("posting_window", ""),
            "posted_at": p.get("posted_at", ""),
            "content_pillar": p.get("content_pillar", ""),
            "target_audience": p.get("target_audience", ""),
            "source_category": p.get("source_category", ""),
            "source_topic": p.get("source_topic", ""),
            "prompt_version": p.get("prompt_version", ""),
            "hypothesis": p.get("hypothesis", ""),
            "like_count": like_count,
            "retweet_count": retweet_count,
            "reply_count": reply_count,
            "engagement_score": engagement_score,
        })

    posts_with_metrics.sort(key=lambda x: x["engagement_score"], reverse=True)

    out = {
        "posts": posts_with_metrics[:50],
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    path = data_dir / "post_metrics.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    fetched = sum(1 for p in posted if metrics_by_id.get(p.get("tweet_id")))
    print(f"保存: {path} ({len(posts_with_metrics)} 件、API取得: {fetched}/{len(ids)} 件)")
