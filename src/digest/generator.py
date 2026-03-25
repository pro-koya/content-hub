"""
Digest Generator
RSSフィードからダイジェストを生成するメインロジック。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.collectors.rss import Article, fetch_category_feeds
from src.digest.config import DigestConfig, load_config
from src.digest.renderer import DigestArticle, render_digest, save_digest
from src.digest.summarizer import summarize

SPECIAL_COLLECTORS = {
    "QIITA_TRENDING",
    "NOTE_TRENDING",
    "X_BUZZ",
}

JST = timezone(timedelta(hours=9))


def _fetch_special(category: str, since_ts: int, limit: int) -> list[Article]:
    """RSS以外の特殊コレクター経由で記事を取得する。"""
    if category == "QIITA_TRENDING":
        from src.collectors.qiita import fetch_trending
        return fetch_trending(since_timestamp=since_ts, limit=limit)
    elif category == "NOTE_TRENDING":
        from src.collectors.note import fetch_note_articles
        return fetch_note_articles(since_timestamp=since_ts, limit=limit)
    elif category == "X_BUZZ":
        from src.collectors.x_trending import fetch_trending_posts
        return fetch_trending_posts(since_timestamp=since_ts, limit=limit)
    return []


def determine_relevance(category: str, relevance_tags: list[str]) -> str:
    if not relevance_tags:
        return ""
    return relevance_tags[0]


def run_digest(config_path: str = "config/digest.yml") -> dict:
    """ダイジェストを生成して保存する。結果のサマリーを返す。"""
    print(f"[{datetime.now(JST).isoformat()}] Digest generation started.")

    config = load_config(config_path)

    now = datetime.now(JST)
    since = now - timedelta(hours=config.lookback_hours)
    since_ts = int(since.timestamp())

    all_digest_articles: dict[str, list[DigestArticle]] = {}
    total_count = 0

    for cat_name, cat_config in config.categories.items():
        if total_count >= config.max_total_items:
            break

        remaining_budget = config.max_total_items - total_count
        effective_max = min(cat_config.max_items, remaining_budget)

        print(f"[{cat_name}] Fetching feeds (max={effective_max})...")

        if cat_name in SPECIAL_COLLECTORS:
            articles = _fetch_special(cat_name, since_ts, effective_max)
        else:
            articles = fetch_category_feeds(
                feeds_config_path=config.feeds_config,
                category=cat_name,
                since_timestamp=since_ts,
                limit=effective_max,
            )

        digest_articles = []
        for art in articles[:effective_max]:
            print(f"  Summarizing: {art.title[:60]}...")
            summary = summarize(
                art.content,
                method=config.summarizer,
                num_sentences=config.summary_sentences,
            )
            relevance = determine_relevance(cat_name, cat_config.relevance_tags)

            digest_articles.append(DigestArticle(
                title=art.title,
                source=art.feed_title,
                url=art.url,
                summary=summary,
                category=cat_name,
                relevance_tag=relevance,
                is_starred=art.is_starred,
            ))

        if digest_articles:
            all_digest_articles[cat_name] = digest_articles
            total_count += len(digest_articles)
            print(f"  -> {len(digest_articles)} articles processed.")

    md_content = render_digest(all_digest_articles, now, config.lookback_hours)

    output_dir = Path(config.output_dir)
    date_str = now.strftime("%Y-%m-%d")
    saved = save_digest(output_dir, md_content, date_str)

    print(f"[{datetime.now(JST).isoformat()}] Digest saved: {saved['dated_md']}")
    print(f"  Total articles: {total_count}")
    print("Done.")

    return {
        "date": date_str,
        "total_articles": total_count,
        "categories": list(all_digest_articles.keys()),
        "output_files": {k: str(v) for k, v in saved.items()},
    }
