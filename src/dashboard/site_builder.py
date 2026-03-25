"""
GitHub Pages 用サイトビルダー
docs/ 配下に統合ダッシュボードを生成する。
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

import json
import re

DOCS_DIR = Path("docs")
DIGESTS_DIR = DOCS_DIR / "digests"
ROOT = Path(__file__).resolve().parent.parent.parent


def _get_digest_entries() -> list[dict]:
    if not DIGESTS_DIR.exists():
        return []
    return [
        {"name": f.name, "date": f.stem}
        for f in sorted(
            [f for f in DIGESTS_DIR.glob("*.html") if f.name != "index.html"],
            reverse=True,
        )
    ]


def _get_xpost_stats() -> dict:
    posted_path = ROOT / "data" / "posted_tweets.json"
    metrics_path = ROOT / "data" / "post_metrics.json"
    stats = {"total_posts": 0, "latest_date": "", "avg_engagement": 0.0, "recent_posts": []}

    if posted_path.exists():
        try:
            data = json.loads(posted_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                stats["total_posts"] = len(data)
                if data:
                    stats["latest_date"] = data[-1].get("date", "")
                    stats["recent_posts"] = [
                        {"date": p.get("date", ""), "text": p.get("text", "")[:60]}
                        for p in data[-5:]
                    ]
        except (json.JSONDecodeError, OSError):
            pass

    if metrics_path.exists():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            posts = data.get("posts", [])
            if posts:
                total_es = sum(p.get("engagement_score", 0) for p in posts)
                stats["avg_engagement"] = round(total_es / len(posts), 1)
        except (json.JSONDecodeError, OSError):
            pass

    return stats


def _get_analysis_entries() -> list[dict]:
    reports_dir = DOCS_DIR / "x-reports"
    if not reports_dir.exists():
        return []
    return [
        {"name": f.name, "date": f.stem.replace("analysis-", "")}
        for f in sorted(reports_dir.glob("analysis-*.md"), reverse=True)
    ]


def _get_article_entries() -> list[dict]:
    articles_dir = DOCS_DIR / "articles"
    if not articles_dir.exists():
        return []
    articles = []
    for path in sorted(articles_dir.glob("*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")
        fm = re.match(r"---\s*\n(.*?)\n---", content, re.DOTALL)
        title = path.stem
        status = "draft"
        if fm:
            t = re.search(r'title:\s*"?([^"\n]+)"?', fm.group(1))
            s = re.search(r'status:\s*"?([^"\n]+)"?', fm.group(1))
            if t:
                title = t.group(1).strip()
            if s:
                status = s.group(1).strip()
        articles.append({"file": path.name, "title": title, "status": status})
    return articles


def build_site() -> dict[str, str]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    template = Template(DASHBOARD_TEMPLATE)
    digest_entries = _get_digest_entries()
    xpost_stats = _get_xpost_stats()
    analysis_entries = _get_analysis_entries()
    article_entries = _get_article_entries()

    html = template.render(
        digest_entries=digest_entries,
        has_digests=len(digest_entries) > 0,
        xpost=xpost_stats,
        analysis_entries=analysis_entries,
        has_analysis=len(analysis_entries) > 0,
        article_entries=article_entries,
        has_articles=len(article_entries) > 0,
    )

    index_path = DOCS_DIR / "index.html"
    index_path.write_text(html, encoding="utf-8")

    nojekyll = DOCS_DIR / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.touch()

    return {"index_path": str(index_path)}


DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Content Hub</title>
  <style>
    :root { --bg: #0d1117; --fg: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --border: #30363d; --card: #161b22; --green: #3fb950; --orange: #d29922; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
           background: var(--bg); color: var(--fg); line-height: 1.7; }
    .container { max-width: 1000px; margin: 0 auto; padding: 2rem; }
    h1 { font-size: 2rem; margin-bottom: 0.5rem; }
    .subtitle { color: var(--muted); margin-bottom: 2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; }
    .card h2 { font-size: 1.2rem; color: var(--accent); margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
    .card ul { list-style: none; }
    .card li { padding: 0.4rem 0; border-bottom: 1px solid var(--border); }
    .card li:last-child { border-bottom: none; }
    .card li.empty { color: var(--muted); font-style: italic; }
    .card a { color: var(--accent); text-decoration: none; }
    .card a:hover { text-decoration: underline; }
    .btn { display: inline-block; margin: 0.5rem 0; padding: 0.5rem 1.2rem; background: var(--accent);
           color: var(--bg); border-radius: 6px; font-weight: bold; text-decoration: none; font-size: 0.9rem; }
    .btn:hover { opacity: 0.9; text-decoration: none; }
    .status { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .status-active { background: rgba(63,185,80,0.15); color: var(--green); }
    .status-planned { background: rgba(210,153,34,0.15); color: var(--orange); }
    .footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Content Hub</h1>
    <p class="subtitle">情報収集 → リサーチ → 記事執筆 → 発信 → フィードバック</p>

    <div class="grid">
      <div class="card">
        <h2>📰 Daily Digest <span class="status status-active">Active</span></h2>
        {% if has_digests %}<a href="digests/index.html" class="btn">Latest Digest</a>{% endif %}
        <ul>
        {% if digest_entries %}
          {% for entry in digest_entries %}
          <li><a href="digests/{{ entry.name }}">{{ entry.date }}</a></li>
          {% endfor %}
        {% else %}
          <li class="empty">まだダイジェストがありません。</li>
        {% endif %}
        </ul>
      </div>

      <div class="card">
        <h2>🐦 X Post <span class="status status-active">Active</span></h2>
        {% if xpost.total_posts > 0 %}
        <div style="margin-bottom: 0.8rem;">
          <div style="display: flex; gap: 1.5rem; color: var(--muted); font-size: 0.85rem;">
            <span>投稿数: <strong style="color: var(--fg);">{{ xpost.total_posts }}</strong></span>
            <span>平均ES: <strong style="color: var(--fg);">{{ xpost.avg_engagement }}</strong></span>
          </div>
        </div>
        {% if has_analysis %}<a href="x-reports/latest.md" class="btn">Latest Analysis</a>{% endif %}
        <ul>
          {% for post in xpost.recent_posts %}
          <li style="font-size: 0.85rem;">{{ post.date }} — {{ post.text }}...</li>
          {% endfor %}
        </ul>
        {% else %}
        <p style="color: var(--muted); font-size: 0.9rem;">まだ投稿がありません。</p>
        {% endif %}
      </div>

      <div class="card">
        <h2>📝 Articles <span class="status status-active">Active</span></h2>
        {% if has_articles %}
        <ul>
          {% for art in article_entries %}
          <li><span class="status {% if art.status == 'published' %}status-active{% else %}status-planned{% endif %}">{{ art.status }}</span> <a href="articles/{{ art.file }}">{{ art.title }}</a></li>
          {% endfor %}
        </ul>
        {% else %}
        <p style="color: var(--muted); font-size: 0.9rem;">まだ記事がありません。<br><code>python cli.py article:generate --topic "テーマ"</code></p>
        {% endif %}
      </div>

      <div class="card">
        <h2>📊 Experiment Analysis <span class="status status-active">Active</span></h2>
        {% if has_analysis %}
        <a href="x-reports/latest.md" class="btn">Latest Report</a>
        <ul>
          {% for entry in analysis_entries %}
          <li><a href="x-reports/{{ entry.name }}">{{ entry.date }}</a></li>
          {% endfor %}
        </ul>
        {% else %}
        <p style="color: var(--muted); font-size: 0.9rem;">まだ分析レポートがありません。</p>
        {% endif %}
      </div>
    </div>

    <div style="margin: 2rem 0;">
      <div class="card">
        <h2>📡 Information Sources</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.5rem; font-size: 0.85rem;">
          <div><span class="status status-active">RSS</span> AI Research / Product / Macro</div>
          <div><span class="status status-active">RSS</span> Japan Signal / Agriculture</div>
          <div><span class="status status-active">RSS</span> AI Driven Dev / Career</div>
          <div><span class="status status-active">API</span> Qiita Trending</div>
          <div><span class="status status-active">RSS</span> note Trending</div>
          <div><span class="status status-active">API</span> X Buzz</div>
        </div>
      </div>
    </div>

    <div class="footer">
      <p>Powered by content-hub &middot; GitHub Actions + Pages</p>
    </div>
  </div>
</body>
</html>"""
