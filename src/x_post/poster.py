"""output ファイルから未投稿の投稿を1件取り出して X に投稿する."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import tweepy

from src.x_post.lint import parse_output_file

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROOT = Path(os.environ.get("GITHUB_WORKSPACE", _REPO_ROOT))
JST = timezone(timedelta(hours=9))


def _today_str() -> str:
    return datetime.now(JST).strftime("%Y%m%d")


def _find_today_file(project: str = "liftly") -> Path | None:
    path = ROOT / "output" / f"{project}_{_today_str()}.md"
    return path if path.exists() else None


def _get_next_unposted(path: Path) -> dict | None:
    posts = parse_output_file(path)
    for post in posts:
        if post["posted"] is None:
            return post
    return None


def _mark_as_posted(path: Path, post_text: str) -> None:
    content = path.read_text(encoding="utf-8")
    now = datetime.now(JST).isoformat(timespec="seconds")
    first_line = post_text.split("\n")[0].strip()
    escaped = re.escape(first_line)

    pattern = re.compile(
        r"(\*\*\[[^\]]+\]\*\*(?:\s*📷)?)\s*\n" + escaped,
    )
    match = pattern.search(content)
    if match:
        old = match.group(0)
        new = f"{match.group(1)} <!-- posted: {now} -->\n{first_line}"
        content = content.replace(old, new, 1)
        path.write_text(content, encoding="utf-8")
        print(f"投稿済みマークを追加: {path.name}")
    else:
        print("WARNING: 投稿済みマークの追加に失敗しました", file=sys.stderr)


def _save_posted_tweet(tweet_id: str, text: str, archetype: str) -> None:
    from src.x_post.experiment import infer_hook_style, infer_tone, infer_cta_type

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    path = data_dir / "posted_tweets.json"
    today = _today_str()
    entry = {
        "date": today,
        "tweet_id": str(tweet_id),
        "text": text,
        "archetype": archetype,
        "hook_style": infer_hook_style(text),
        "tone": infer_tone(text),
        "cta_type": infer_cta_type(text),
        "posting_window": datetime.now(JST).strftime("%H:%M"),
    }
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []
        if not isinstance(existing, list):
            existing = []
    else:
        existing = []
    existing.append(entry)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"記録: data/posted_tweets.json に tweet_id={tweet_id} を追加")


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


def post_to_x(dry_run: bool = False, project: str = "liftly") -> bool:
    path = _find_today_file(project)
    if not path:
        print(f"今日の output ファイルが見つかりません: {project}_{_today_str()}.md")
        return False

    post = _get_next_unposted(path)
    if not post:
        print("未投稿の投稿がありません。スキップします。")
        return False

    text = post["text"]
    print(f"投稿予定 [{post['archetype']}]:")
    print(f"  {text}")
    print(f"  ({len(text)}文字)")

    if dry_run:
        print("DRY RUN: 実際には投稿しません")
        return True

    client = _create_x_client()
    response = client.create_tweet(text=text)
    tweet_id = response.data["id"]
    print(f"投稿完了: https://x.com/i/status/{tweet_id}")

    _mark_as_posted(path, text)
    _save_posted_tweet(tweet_id=tweet_id, text=text, archetype=post["archetype"])
    return True
