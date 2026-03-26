"""
軽量な実験分析モジュール
投稿の比較軸（hook_style, tone, cta_type, posting_window）と
メトリクスを突合し、どの軸が効いているかを分析する。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.x_post.config import get_default_project

ROOT = Path(__file__).resolve().parent.parent.parent
JST = timezone(timedelta(hours=9))

AXIS_KEYS = [
    "hook_style",
    "tone",
    "cta_type",
    "posting_window",
    "archetype",
    "content_pillar",
    "source_category",
    "target_audience",
]


@dataclass
class PostRecord:
    tweet_id: str
    date: str
    text: str
    archetype: str
    project: str = ""
    hook_style: str = ""
    tone: str = ""
    cta_type: str = ""
    posting_window: str = ""
    content_pillar: str = ""
    target_audience: str = ""
    source_category: str = ""
    source_topic: str = ""
    prompt_version: str = ""
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    engagement_score: int = 0


@dataclass
class AxisAnalysis:
    axis_name: str
    value: str
    count: int = 0
    avg_engagement: float = 0.0
    avg_likes: float = 0.0
    avg_retweets: float = 0.0
    total_impressions: int = 0


def infer_hook_style(text: str) -> str:
    """投稿本文からフックスタイルを推定する。"""
    first_line = text.split("\n")[0].strip()
    if re.search(r"[？?]", first_line):
        return "question"
    if re.search(r"してみたら|やってみたら|気づいた|分かった", first_line):
        return "experience"
    if re.search(r"なんていうか|結局|思うんだけど", first_line):
        return "reflection"
    if re.search(r"話題|トレンド|流行|最近", first_line):
        return "trend"
    if re.search(r"[0-9０-９]", first_line):
        return "data-driven"
    return "statement"


def infer_tone(text: str) -> str:
    """投稿本文からトーンを推定する。"""
    casual_markers = ["だよね", "なんか", "っていう", "じゃないか", "かも"]
    philosophical_markers = ["選ぶ", "決める", "問い", "哲学", "本質"]
    practical_markers = ["やってみて", "してみて", "コツ", "方法", "ステップ"]

    casual_score = sum(1 for m in casual_markers if m in text)
    philosophical_score = sum(1 for m in philosophical_markers if m in text)
    practical_score = sum(1 for m in practical_markers if m in text)

    if philosophical_score >= 2:
        return "philosophical"
    if practical_score >= 2:
        return "practical"
    if casual_score >= 2:
        return "casual"
    return "balanced"


def infer_cta_type(text: str) -> str:
    """CTA の種類を推定する。"""
    if re.search(r"リンク|プロフ|ダウンロード|インストール", text):
        return "hard"
    if re.search(r"気になる人|試してみて|やってみて", text):
        return "soft"
    return "none"


def infer_posting_window(date_str: str) -> str:
    """投稿日時から時間帯を推定する。日付のみの場合はデフォルト morning。"""
    if "T" in date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            hour = dt.hour
            if 5 <= hour < 12:
                return "morning"
            elif 12 <= hour < 17:
                return "afternoon"
            elif 17 <= hour < 22:
                return "evening"
            else:
                return "night"
        except ValueError:
            pass
    if re.match(r"^\d{2}:\d{2}$", date_str):
        hour = int(date_str.split(":", 1)[0])
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        return "night"
    return "morning"


def _normalized_project(tweet: dict) -> str:
    return str(tweet.get("project") or "liftly")


def enrich_post_record(tweet: dict) -> PostRecord:
    """posted_tweets + metrics データから比較軸を推定して PostRecord を生成する。"""
    text = tweet.get("text", "")
    return PostRecord(
        tweet_id=tweet.get("tweet_id", ""),
        date=tweet.get("date", ""),
        text=text,
        archetype=tweet.get("archetype", ""),
        project=_normalized_project(tweet),
        hook_style=tweet.get("hook_style") or infer_hook_style(text),
        tone=tweet.get("tone") or infer_tone(text),
        cta_type=tweet.get("cta_type") or infer_cta_type(text),
        posting_window=tweet.get("posting_window") or infer_posting_window(tweet.get("posted_at", "") or tweet.get("date", "")),
        content_pillar=tweet.get("content_pillar", ""),
        target_audience=tweet.get("target_audience", ""),
        source_category=tweet.get("source_category", ""),
        source_topic=tweet.get("source_topic", ""),
        prompt_version=tweet.get("prompt_version", ""),
        like_count=int(tweet.get("like_count", 0)),
        retweet_count=int(tweet.get("retweet_count", 0)),
        reply_count=int(tweet.get("reply_count", 0)),
        engagement_score=int(tweet.get("engagement_score", 0)),
    )


def load_enriched_records(project: str | None = None) -> list[PostRecord]:
    """posted_tweets + metrics を統合し、比較軸付きの PostRecord リストを返す。"""
    metrics_path = ROOT / "data" / "post_metrics.json"
    tweets_path = ROOT / "data" / "posted_tweets.json"

    posts_data: list[dict] = []
    if metrics_path.exists():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            posts_data = data.get("posts", [])
        except (json.JSONDecodeError, OSError):
            pass

    if not posts_data and tweets_path.exists():
        try:
            posts_data = json.loads(tweets_path.read_text(encoding="utf-8"))
            if not isinstance(posts_data, list):
                posts_data = []
        except (json.JSONDecodeError, OSError):
            pass

    records = [enrich_post_record(p) for p in posts_data]
    if project:
        records = [record for record in records if record.project == project]
    return records


def analyze_axis(records: list[PostRecord], axis: str) -> list[AxisAnalysis]:
    """指定した比較軸でグルーピングし、パフォーマンスを分析する。"""
    groups: dict[str, list[PostRecord]] = defaultdict(list)
    for r in records:
        value = getattr(r, axis, "unknown")
        if value:
            groups[value].append(r)

    results = []
    for value, group in sorted(groups.items()):
        n = len(group)
        avg_eng = sum(r.engagement_score for r in group) / n if n else 0
        avg_likes = sum(r.like_count for r in group) / n if n else 0
        avg_rts = sum(r.retweet_count for r in group) / n if n else 0

        results.append(AxisAnalysis(
            axis_name=axis,
            value=value,
            count=n,
            avg_engagement=round(avg_eng, 2),
            avg_likes=round(avg_likes, 2),
            avg_retweets=round(avg_rts, 2),
        ))

    results.sort(key=lambda a: a.avg_engagement, reverse=True)
    return results


def generate_weekly_analysis(records: list[PostRecord] | None = None) -> str:
    """全比較軸の分析結果を Markdown レポートとして生成する。"""
    if records is None:
        records = load_enriched_records()

    if not records:
        return "# 週次実験分析レポート\n\nデータがありません。投稿とメトリクス取得を実行してください。\n"

    now = datetime.now(JST)
    lines = [
        f"# 週次実験分析レポート",
        f"",
        f"**生成日時:** {now.strftime('%Y-%m-%d %H:%M JST')}",
        f"**分析対象:** {len(records)} 件の投稿",
        "",
        "---",
        "",
    ]

    for axis in AXIS_KEYS:
        analysis = analyze_axis(records, axis)
        if not analysis:
            continue

        axis_label = {
            "hook_style": "フックスタイル",
            "tone": "トーン",
            "cta_type": "CTA種別",
            "posting_window": "投稿時間帯",
            "archetype": "アーキタイプ",
            "content_pillar": "コンテンツピラー",
            "source_category": "ニュースカテゴリ",
            "target_audience": "ターゲット読者",
        }.get(axis, axis)

        lines.append(f"## {axis_label}")
        lines.append("")
        lines.append("| 値 | 件数 | 平均ES | 平均いいね | 平均RT |")
        lines.append("|---|---|---|---|---|")
        for a in analysis:
            lines.append(f"| {a.value} | {a.count} | {a.avg_engagement} | {a.avg_likes} | {a.avg_retweets} |")
        lines.append("")

        if analysis and analysis[0].count >= 2:
            best = analysis[0]
            lines.append(f"> **推奨:** `{best.value}` が最も高いエンゲージメント（平均ES: {best.avg_engagement}）")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by content-hub experiment analyzer*")

    return "\n".join(lines)


def _render_analysis_html(md_content: str, date_str: str) -> str:
    """分析レポートの Markdown を HTML に変換する。"""
    import markdown as md_lib
    html_body = md_lib.markdown(md_content, extensions=["extra", "sane_lists", "tables"])

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>実験分析レポート - {date_str}</title>
  <style>
    :root {{ --bg: #0d1117; --fg: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --border: #30363d; --card: #161b22; --green: #3fb950; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
           background: var(--bg); color: var(--fg); line-height: 1.7; padding: 2rem; max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
    h2 {{ font-size: 1.3rem; color: var(--accent); margin-top: 2rem; margin-bottom: 0.8rem; }}
    p {{ margin: 0.5rem 0; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
    blockquote {{ border-left: 3px solid var(--green); padding: 0.5rem 1rem; margin: 0.8rem 0;
                 background: var(--card); border-radius: 0 6px 6px 0; }}
    strong {{ color: var(--fg); }}
    code {{ background: var(--card); padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em; color: var(--green); }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th {{ background: var(--card); color: var(--accent); text-align: left; padding: 0.6rem 1rem; border: 1px solid var(--border); font-size: 0.9rem; }}
    td {{ padding: 0.5rem 1rem; border: 1px solid var(--border); font-size: 0.9rem; }}
    tr:hover td {{ background: rgba(88,166,255,0.05); }}
    .back {{ display: inline-block; margin-bottom: 1rem; color: var(--accent); font-size: 0.9rem; }}
    .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <a href="../index.html" class="back">&larr; Dashboard に戻る</a>
  {html_body}
  <div class="footer"><p>Powered by content-hub</p></div>
</body>
</html>"""


def save_analysis_report(report_md: str) -> Path:
    """分析レポートを docs/x-reports/ に HTML + Markdown で保存する。"""
    reports_dir = ROOT / "docs" / "x-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(JST)
    date_str = now.strftime("%Y-%m-%d")

    report_path_md = reports_dir / f"analysis-{date_str}.md"
    report_path_md.write_text(report_md, encoding="utf-8")

    html = _render_analysis_html(report_md, date_str)
    report_path_html = reports_dir / f"analysis-{date_str}.html"
    report_path_html.write_text(html, encoding="utf-8")

    (reports_dir / "latest.md").write_text(report_md, encoding="utf-8")
    (reports_dir / "latest.html").write_text(html, encoding="utf-8")
    (reports_dir / "index.html").write_text(html, encoding="utf-8")

    return report_path_html


def get_prompt_insights(records: list[PostRecord] | None = None, project: str | None = None) -> str:
    """分析結果からプロンプトに注入するインサイトを生成する。"""
    if records is None:
        records = load_enriched_records(project=project or get_default_project())

    if len(records) < 3:
        return ""

    insights = ["## 過去の分析から得た傾向（参考にすること）", ""]

    for axis in ["hook_style", "tone", "archetype", "content_pillar", "source_category"]:
        analysis = analyze_axis(records, axis)
        if analysis and analysis[0].count >= 2:
            best = analysis[0]
            axis_label = {
                "hook_style": "フックスタイル",
                "tone": "トーン",
                "archetype": "アーキタイプ",
                "content_pillar": "コンテンツピラー",
                "source_category": "ニュースカテゴリ",
            }.get(axis, axis)
            insights.append(f"- **{axis_label}**: `{best.value}` が最も反応が良い（平均ES: {best.avg_engagement}、{best.count}件）")

    if len(insights) > 2:
        return "\n".join(insights)
    return ""
