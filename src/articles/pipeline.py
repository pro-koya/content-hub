"""
記事執筆パイプライン
ダイジェストや収集した情報をもとに、記事のドラフトを生成する。
LLM（Gemini）を使ったリサーチ→構成→執筆のフローを提供する。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent.parent
JST = timezone(timedelta(hours=9))


@dataclass
class ArticleDraft:
    title: str
    slug: str
    category: str
    content: str
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    status: str = "draft"


def _load_latest_digest() -> str:
    """最新のダイジェストから記事ネタの候補を取得する。"""
    latest_path = ROOT / "docs" / "digests" / "latest.md"
    if latest_path.exists():
        return latest_path.read_text(encoding="utf-8")[:5000]
    return ""


def _load_analysis_insights() -> str:
    """X投稿の分析結果から傾向を取得する。"""
    latest_path = ROOT / "docs" / "x-reports" / "latest.md"
    if latest_path.exists():
        return latest_path.read_text(encoding="utf-8")[:3000]
    return ""


ARTICLE_PROMPT_TEMPLATE = """あなたは「筋トレが趣味の個人開発者」のブログ記事執筆アシスタントです。

## 記事の方針
- **対象読者**: AI駆動開発に興味のあるエンジニア、兼業農家に興味がある人、筋トレ好きの個人開発者
- **トーン**: 哲学的だがラフ。技術記事でも「自分はこう思う」という視点を入れる
- **文体**: です・ます調ではなく、だ・である調。ただし堅くなりすぎない
- **構成**: 導入（フック）→ 本論（3-5セクション）→ まとめ（アクション提案）

## カテゴリ
記事のカテゴリは以下から選択:
- ai-driven-dev: AI駆動開発（ツール、手法、ベストプラクティス）
- agriculture: 農業・兼業農家（スマート農業、体験、考察）
- career: キャリア形成（フリーランス、エンジニア×農業）
- fitness-tech: 筋トレ×テクノロジー（記録、AI活用、アプリ開発）
- weekly-review: 週次振り返り（今週の気づき、学び）

## 最新ダイジェストからの情報

{digest_context}

## X投稿の反応分析

{analysis_context}

## 生成指示

テーマ: **{topic}**

以下の構成で記事を生成してください:

1. タイトル（60文字以内、興味を引くフック）
2. リード文（3行程度。何が書かれているか分かるように）
3. 本文（Markdown形式、見出し付き、1500-3000文字）
4. まとめ（読者へのアクション提案を含む）
5. タグ（3-5個）

### 出力フォーマット

```markdown
---
title: "タイトル"
category: "カテゴリ"
tags: ["タグ1", "タグ2", "タグ3"]
date: "{today}"
status: "draft"
---

（本文をここに）
```
"""


def _parse_article_output(text: str) -> ArticleDraft | None:
    """生成された記事テキストを解析する。"""
    code_match = re.search(r"```(?:markdown)?\s*\n(.*?)```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    frontmatter_match = re.match(r"---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not frontmatter_match:
        return ArticleDraft(
            title="Untitled",
            slug="untitled",
            category="general",
            content=text,
            created_at=datetime.now(JST).isoformat(),
        )

    fm_text = frontmatter_match.group(1)
    body = frontmatter_match.group(2).strip()

    title = re.search(r'title:\s*"?([^"\n]+)"?', fm_text)
    category = re.search(r'category:\s*"?([^"\n]+)"?', fm_text)
    tags_match = re.search(r'tags:\s*\[([^\]]*)\]', fm_text)

    title_str = title.group(1).strip() if title else "Untitled"
    category_str = category.group(1).strip() if category else "general"

    tags = []
    if tags_match:
        tags = [t.strip().strip('"').strip("'") for t in tags_match.group(1).split(",")]

    slug = re.sub(r"[^\w\s-]", "", title_str.lower())
    slug = re.sub(r"[\s_]+", "-", slug)[:60]

    return ArticleDraft(
        title=title_str,
        slug=slug,
        category=category_str,
        content=body,
        tags=tags,
        created_at=datetime.now(JST).isoformat(),
    )


def generate_article(topic: str, category: str = "") -> ArticleDraft | None:
    """指定トピックで記事ドラフトを生成する。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません", file=sys.stderr)
        return None

    digest_context = _load_latest_digest() or "(ダイジェストなし)"
    analysis_context = _load_analysis_insights() or "(分析データなし)"
    today = datetime.now(JST).strftime("%Y-%m-%d")

    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        digest_context=digest_context,
        analysis_context=analysis_context,
        topic=topic,
        today=today,
    )

    client = genai.Client(api_key=api_key)
    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    print(f"記事を生成中: {topic}")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8192,
            tools=[google_search_tool],
        ),
    )

    draft = _parse_article_output(response.text)
    if draft and category:
        draft.category = category

    return draft


def _render_article_html(draft: ArticleDraft, date_str: str) -> str:
    """記事ドラフトの Markdown を HTML に変換する。"""
    import markdown as md_lib
    html_body = md_lib.markdown(draft.content, extensions=["extra", "sane_lists", "tables", "fenced_code"])

    tags_html = " ".join(
        f'<span style="display:inline-block;padding:0.15rem 0.5rem;border-radius:12px;'
        f'font-size:0.8rem;background:rgba(88,166,255,0.15);color:#58a6ff;margin-right:0.3rem;">{t}</span>'
        for t in draft.tags
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{draft.title}</title>
  <style>
    :root {{ --bg: #0d1117; --fg: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --border: #30363d; --card: #161b22; --green: #3fb950; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
           background: var(--bg); color: var(--fg); line-height: 1.8; padding: 2rem; max-width: 800px; margin: 0 auto; }}
    h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
    h2 {{ font-size: 1.4rem; color: var(--accent); margin-top: 2rem; margin-bottom: 0.8rem; }}
    h3 {{ font-size: 1.15rem; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
    p {{ margin: 0.8rem 0; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
    blockquote {{ border-left: 3px solid var(--accent); padding: 0.5rem 1rem; margin: 0.8rem 0;
                 background: var(--card); border-radius: 0 6px 6px 0; color: var(--muted); }}
    strong {{ color: var(--fg); }}
    code {{ background: var(--card); padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em; }}
    pre {{ background: var(--card); padding: 1rem; border-radius: 6px; overflow-x: auto; margin: 1rem 0; }}
    pre code {{ background: none; padding: 0; }}
    ul, ol {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
    li {{ margin: 0.3rem 0; }}
    .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }}
    .tags {{ margin: 0.5rem 0; }}
    .back {{ display: inline-block; margin-bottom: 1rem; color: var(--accent); font-size: 0.9rem; }}
    .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <a href="../index.html" class="back">&larr; Dashboard に戻る</a>
  <h1>{draft.title}</h1>
  <div class="meta">
    <span>{date_str}</span> &middot;
    <span>{draft.category}</span> &middot;
    <span style="text-transform:uppercase;color:{'var(--green)' if draft.status == 'published' else 'var(--muted)'};">{draft.status}</span>
  </div>
  <div class="tags">{tags_html}</div>
  <hr>
  {html_body}
  <div class="footer"><p>Powered by content-hub</p></div>
</body>
</html>"""


def save_article(draft: ArticleDraft) -> Path:
    """記事ドラフトを docs/articles/ に HTML + Markdown で保存する。"""
    articles_dir = ROOT / "docs" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(JST).strftime("%Y-%m-%d")
    slug = draft.slug or "untitled"

    md_filename = f"{date_str}-{slug}.md"
    md_path = articles_dir / md_filename
    frontmatter = f"""---
title: "{draft.title}"
category: "{draft.category}"
tags: {json.dumps(draft.tags, ensure_ascii=False)}
date: "{date_str}"
status: "{draft.status}"
---

"""
    md_path.write_text(frontmatter + draft.content, encoding="utf-8")

    html_filename = f"{date_str}-{slug}.html"
    html_path = articles_dir / html_filename
    html = _render_article_html(draft, date_str)
    html_path.write_text(html, encoding="utf-8")

    print(f"記事ドラフト保存: {md_path} / {html_path}")
    return html_path


def list_articles() -> list[dict]:
    """保存済みの記事一覧を返す。"""
    articles_dir = ROOT / "docs" / "articles"
    if not articles_dir.exists():
        return []

    articles = []
    for path in sorted(articles_dir.glob("*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")
        fm_match = re.match(r"---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            title = re.search(r'title:\s*"?([^"\n]+)"?', fm)
            category = re.search(r'category:\s*"?([^"\n]+)"?', fm)
            status = re.search(r'status:\s*"?([^"\n]+)"?', fm)
            articles.append({
                "file": path.name,
                "title": title.group(1).strip() if title else path.stem,
                "category": category.group(1).strip() if category else "general",
                "status": status.group(1).strip() if status else "draft",
            })
        else:
            articles.append({
                "file": path.name,
                "title": path.stem,
                "category": "general",
                "status": "draft",
            })

    return articles
