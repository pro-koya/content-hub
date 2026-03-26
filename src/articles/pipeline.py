"""
記事執筆パイプライン
ダイジェストや収集した情報をもとに、記事のドラフトを生成する。
LLM（Gemini）が利用できる場合は LLM を使い、未設定時はローカル情報から
記事草稿を組み立てるフォールバックを提供する。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JST = timezone(timedelta(hours=9))

CATEGORY_OPTIONS = {
    "ai-driven-dev": "AI駆動開発",
    "agriculture": "農業・兼業農家",
    "career": "キャリア形成",
    "general": "総合",
}

CATEGORY_KEYWORDS = {
    "ai-driven-dev": ["AI", "LLM", "RAG", "agent", "開発", "コーディング", "生成AI", "自動化"],
    "agriculture": ["農業", "農家", "agritech", "smart farming", "precision agriculture"],
    "career": ["キャリア", "副業", "フリーランス", "複業", "働き方", "収入"],
}

LOW_SIGNAL_PATTERNS = (
    "要約する記事本文が提示されていません",
    "記事本文が提供されていない",
    "Comments",
    "(本文なし)",
)


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


@dataclass
class DigestSource:
    category: str
    title: str
    source: str
    url: str
    summary: str
    relevance: str = ""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:60] or "untitled"


def _read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_latest_digest() -> str:
    return _read_text(ROOT / "docs" / "digests" / "latest.md")


def _load_analysis_report() -> str:
    return _read_text(ROOT / "docs" / "x-reports" / "latest.md")


def _category_from_digest_heading(heading: str) -> str:
    normalized = heading.strip().lower()
    if "ai driven development" in normalized:
        return "ai-driven-dev"
    if "agriculture" in normalized:
        return "agriculture"
    if "career" in normalized:
        return "career"
    if "qiita trending" in normalized:
        return "ai-driven-dev"
    if "x buzz" in normalized:
        return "ai-driven-dev"
    return "general"


def _parse_digest_sources(markdown: str) -> list[DigestSource]:
    if not markdown:
        return []

    sources: list[DigestSource] = []
    current_heading = "general"
    current_item: dict[str, str] | None = None
    summary_lines: list[str] = []

    def flush_item() -> None:
        nonlocal current_item, summary_lines
        if not current_item:
            return
        summary = " ".join(summary_lines).strip()
        if summary and not any(pattern in summary for pattern in LOW_SIGNAL_PATTERNS):
            sources.append(DigestSource(
                category=current_item["category"],
                title=current_item["title"],
                source=current_item["source"],
                url=current_item["url"],
                summary=summary,
                relevance=current_item.get("relevance", ""),
            ))
        current_item = None
        summary_lines = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            flush_item()
            current_heading = _category_from_digest_heading(line[3:])
            continue
        if line.startswith("### "):
            flush_item()
            current_item = {
                "category": current_heading,
                "title": re.sub(r"^\d+\.\s*", "", line[4:]).strip(),
                "source": "",
                "url": "",
                "relevance": "",
            }
            continue
        if not current_item:
            continue
        if line.startswith("**出典:**"):
            source_match = re.search(r"\*\*出典:\*\*\s*(.*?)\s*\|\s*\[記事リンク\]\((https?://[^)]+)\)", line)
            if source_match:
                current_item["source"] = source_match.group(1).strip()
                current_item["url"] = source_match.group(2).strip()
            else:
                current_item["source"] = line.replace("**出典:**", "").strip()
            continue
        if line.startswith("> "):
            summary_lines.append(line[2:].strip())
            continue
        if line.startswith("**転用示唆:**"):
            current_item["relevance"] = line.replace("**転用示唆:**", "").strip()

    flush_item()
    return sources


def _topic_keywords(topic: str, category: str) -> list[str]:
    keywords = [k for k in re.findall(r"[A-Za-z0-9][A-Za-z0-9-+_.]*|[一-龥ぁ-んァ-ヶ]{2,}", topic)]
    keywords.extend(CATEGORY_KEYWORDS.get(category, []))
    seen: set[str] = set()
    ordered: list[str] = []
    for keyword in keywords:
        lowered = keyword.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(keyword)
    return ordered


def _score_digest_source(item: DigestSource, topic: str, category: str) -> int:
    haystack = " ".join([item.title, item.summary, item.source, item.category, item.relevance]).lower()
    score = 0
    if category and item.category == category:
        score += 5
    for keyword in _topic_keywords(topic, category):
        if keyword.lower() in haystack:
            score += 2
    if item.relevance:
        score += 1
    return score


def _select_digest_sources(topic: str, category: str, limit: int = 5) -> list[DigestSource]:
    markdown = _load_latest_digest()
    items = _parse_digest_sources(markdown)
    if not items:
        return []
    ranked = sorted(
        items,
        key=lambda item: (_score_digest_source(item, topic, category), item.category == category, len(item.summary)),
        reverse=True,
    )
    selected = [item for item in ranked if _score_digest_source(item, topic, category) > 0][:limit]
    if selected:
        return selected
    return ranked[:limit]


def _build_digest_context(topic: str, category: str) -> tuple[str, list[DigestSource]]:
    sources = _select_digest_sources(topic, category)
    if not sources:
        return "(ダイジェストなし)", []

    lines = ["以下は記事執筆で優先的に参照した最新トピックです。"]
    for item in sources:
        lines.append(f"- [{CATEGORY_OPTIONS.get(item.category, item.category)}] {item.title}")
        lines.append(f"  要点: {item.summary}")
        if item.relevance:
            lines.append(f"  転用示唆: {item.relevance}")
        if item.url:
            lines.append(f"  URL: {item.url}")
    return "\n".join(lines), sources


def _extract_analysis_highlights(report: str) -> list[str]:
    if not report:
        return []
    highlights = []
    for line in report.splitlines():
        line = line.strip()
        if line.startswith("> **推奨:**"):
            highlights.append(line.replace("> **推奨:**", "").strip())
    return highlights


ARTICLE_PROMPT_TEMPLATE = """あなたは Content Hub の記事執筆アシスタントです。

## 記事の目的
- 最新の情報収集結果をもとに、読者が「今なぜ重要か」と「自分ならどう活かすか」を理解できる記事にする
- 読者は AI駆動開発、兼業農家、キャリア形成に関心がある
- 断定しすぎず、情報から読み取れる示唆と筆者の視点を両立する

## 記事の方針
- 文体は「だ・である調」を基本にする
- 単なる要約ではなく、複数ソースを束ねた解釈を入れる
- 見出しは 4-5 個程度にする
- 参考にした情報の URL を前提に、不自然な固有名詞の言い換えはしない

## 最新ダイジェストからの情報

{digest_context}

## X投稿の反応分析

{analysis_context}

## 生成指示

テーマ: **{topic}**
カテゴリ: **{category_label}**

以下の構成で記事を生成してください。

1. タイトル（60文字以内）
2. リード文（2-3段落）
3. 本文（Markdown形式、見出し付き、1500-3000文字）
4. まとめ（読者への次のアクションを含む）
5. タグ（3-5個）
6. sources: 参照した URL を 2件以上

### 出力フォーマット

```markdown
---
title: "タイトル"
category: "{category}"
tags: ["タグ1", "タグ2", "タグ3"]
sources: ["https://example.com/1", "https://example.com/2"]
date: "{today}"
status: "draft"
---

（本文をここに）
```
"""


def _parse_list_field(fm_text: str, field_name: str) -> list[str]:
    match = re.search(rf"{field_name}:\s*\[([^\]]*)\]", fm_text)
    if not match:
        return []
    values = []
    for item in match.group(1).split(","):
        value = item.strip().strip('"').strip("'")
        if value:
            values.append(value)
    return values


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
    title_str = title.group(1).strip() if title else "Untitled"
    category_str = category.group(1).strip() if category else "general"

    return ArticleDraft(
        title=title_str,
        slug=_slugify(title_str),
        category=category_str,
        content=body,
        tags=_parse_list_field(fm_text, "tags"),
        sources=_parse_list_field(fm_text, "sources"),
        created_at=datetime.now(JST).isoformat(),
    )


def _choose_category(topic: str, category: str, sources: list[DigestSource]) -> str:
    if category:
        return category
    counts: dict[str, int] = {}
    for item in sources:
        counts[item.category] = counts.get(item.category, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    topic_lower = topic.lower()
    if any(keyword.lower() in topic_lower for keyword in CATEGORY_KEYWORDS["agriculture"]):
        return "agriculture"
    if any(keyword.lower() in topic_lower for keyword in CATEGORY_KEYWORDS["career"]):
        return "career"
    return "ai-driven-dev"


def _topic_tags(topic: str, category: str) -> list[str]:
    tags = [CATEGORY_OPTIONS.get(category, category)]
    mapping = {
        "ai-driven-dev": ["AI駆動開発", "情報収集", "ワークフロー設計"],
        "agriculture": ["農業", "スマート農業", "現場改善"],
        "career": ["キャリア形成", "複業", "働き方"],
        "general": ["情報発信", "リサーチ", "実践知"],
    }
    tags.extend(mapping.get(category, mapping["general"]))
    for token in re.findall(r"[一-龥ぁ-んァ-ヶA-Za-z0-9]{2,}", topic):
        if token not in tags:
            tags.append(token)
        if len(tags) >= 8:
            break
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(tag)
    return deduped[:5]


def _trim_text(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    for marker in ("はじめに ", "あなたのマシンに", "こんにちは、"):
        if compact.startswith(marker):
            if "。 " in compact:
                compact = compact.split("。 ", 1)[1].strip()
            elif "。\" " in compact:
                compact = compact.split("。\" ", 1)[1].strip()
    compact = compact.replace("今すぐこの記事を読んでください。", "").strip()
    if len(compact) <= limit:
        return compact
    clipped = compact[:limit].rstrip(" 、,")
    last_stop = max(clipped.rfind("。"), clipped.rfind("、"), clipped.rfind("."))
    if last_stop >= 60:
        clipped = clipped[: last_stop + 1]
    return clipped.rstrip() + "…"


def _short_title(title: str, limit: int = 32) -> str:
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def _build_fallback_body(topic: str, category: str, sources: list[DigestSource], analysis_highlights: list[str]) -> str:
    category_label = CATEGORY_OPTIONS.get(category, category)
    top = sources[:3]
    related_titles = "、".join(_short_title(item.title) for item in top) if top else "最新ダイジェスト"
    lead = (
        f"{topic}を考えるとき、単発のニュースを追うだけでは判断を誤りやすい。"
        f"今の変化は、{related_titles}のような複数の動きをまとめて見たときに輪郭が出る。"
    )
    body_parts = [
        lead,
        "",
        "## なぜ今このテーマなのか",
        f"今回のダイジェストでは、{category_label}に関係する話題が複数並んでいた。"
        "共通しているのは、単なる新機能や新論文の話ではなく、"
        "現場の意思決定をどう変えるかという論点が前に出てきていることだ。"
        "だからこそ、情報収集の段階で終わらせず、記事として自分なりの判断軸に変換する意味がある。",
        "",
        "## 最新情報から見えた変化",
    ]

    for item in top:
        summary = _trim_text(item.summary, limit=220)
        body_parts.append(
            f"### {item.title}\n"
            f"{summary}\n"
            f"ここから読み取れるのは、"
            f"{'安全性と運用設計を最初から記事の論点に入れるべきだということだ' if '攻撃' in item.summary or '安全' in item.summary else '導入手順そのものより、継続的に回せる仕組みへ翻訳する視点が重要だということだ'}。"
            f" {topic}という文脈に置き直すと、"
            f"「何が起きたか」だけでなく「自分ならどの工程から試すか」まで書ける。"
        )

    body_parts.extend([
        "",
        "## 記事にするときの切り口",
        "価値のある記事にするには、情報を並べるだけでは足りない。"
        "読者が知りたいのは、最新トピックの要約ではなく、"
        "それが自分の仕事や日々の判断にどう効くかである。"
        f"その意味で、{topic}では「導入コスト」「現場への接続」「継続運用のしやすさ」を軸に整理するのがよい。",
    ])

    if analysis_highlights:
        body_parts.extend([
            "",
            "## 発信までつなぐ視点",
            "Xの反応分析を見ると、発信で刺さっているのは単なる事実紹介よりも、"
            "問いや立場が見える書き方だった。"
            "記事でも同じで、ニュースの要約だけで終わるより、"
            "自分はどこに可能性を見ているかを一段足したほうが読み手に残る。",
        ])
        for highlight in analysis_highlights[:3]:
            body_parts.append(f"- {highlight}")

    body_parts.extend([
        "",
        "## まとめ",
        f"{topic}を記事にするときは、最新情報を増やすことより、"
        "複数の情報から自分の判断軸を言語化することが重要になる。"
        "まずはダイジェストから関連トピックを3件ほど選び、"
        "共通点と違いを書き出した上で、"
        "最後に自分ならどう試すかまで落とし込む。"
        "その一手間が、単なる要約と価値のある記事の差になる。",
    ])
    return "\n\n".join(body_parts)


def _build_fallback_draft(topic: str, category: str, digest_sources: list[DigestSource], analysis_report: str) -> ArticleDraft:
    resolved_category = _choose_category(topic, category, digest_sources)
    title_prefix = CATEGORY_OPTIONS.get(resolved_category, "最新動向")
    title = f"{title_prefix}の最新情報を記事価値に変える方法"
    analysis_highlights = _extract_analysis_highlights(analysis_report)
    unique_sources = []
    for item in digest_sources:
        if item.url and item.url not in unique_sources:
            unique_sources.append(item.url)
    body = _build_fallback_body(topic, resolved_category, digest_sources, analysis_highlights)
    return ArticleDraft(
        title=title[:60],
        slug=_slugify(title),
        category=resolved_category,
        content=body,
        sources=unique_sources[:5],
        tags=_topic_tags(topic, resolved_category),
        created_at=datetime.now(JST).isoformat(),
    )


def _llm_generate_article(prompt: str):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    return client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8192,
            tools=[google_search_tool],
        ),
    )


def generate_article(topic: str, category: str = "") -> ArticleDraft | None:
    """指定トピックで記事ドラフトを生成する。"""
    digest_context, digest_sources = _build_digest_context(topic, category)
    analysis_report = _load_analysis_report()
    analysis_context = analysis_report[:3000] if analysis_report else "(分析データなし)"
    today = datetime.now(JST).strftime("%Y-%m-%d")
    resolved_category = _choose_category(topic, category, digest_sources)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY 未設定のため、ローカル情報のみで記事ドラフトを生成します。")
        return _build_fallback_draft(topic, resolved_category, digest_sources, analysis_report)

    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        digest_context=digest_context,
        analysis_context=analysis_context,
        topic=topic,
        category=resolved_category,
        category_label=CATEGORY_OPTIONS.get(resolved_category, resolved_category),
        today=today,
    )

    print(f"記事を生成中: {topic}")
    response = _llm_generate_article(prompt)
    draft = _parse_article_output(response.text)
    if not draft:
        return None

    draft.category = resolved_category
    if not draft.tags:
        draft.tags = _topic_tags(topic, resolved_category)
    if not draft.sources:
        draft.sources = [item.url for item in digest_sources if item.url][:5]
    if not draft.created_at:
        draft.created_at = datetime.now(JST).isoformat()
    if not draft.slug:
        draft.slug = _slugify(draft.title)
    return draft


def _build_sources_section(draft: ArticleDraft) -> str:
    if not draft.sources:
        return ""
    lines = ["", "## 参考にした情報"]
    for url in draft.sources:
        lines.append(f"- {url}")
    return "\n".join(lines)


def _render_article_html(draft: ArticleDraft, date_str: str) -> str:
    """記事ドラフトの Markdown を HTML に変換する。"""
    import markdown as md_lib

    rendered_content = draft.content + _build_sources_section(draft)
    html_body = md_lib.markdown(rendered_content, extensions=["extra", "sane_lists", "tables", "fenced_code"])

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
sources: {json.dumps(draft.sources, ensure_ascii=False)}
date: "{date_str}"
status: "{draft.status}"
---

"""
    md_path.write_text(frontmatter + draft.content + _build_sources_section(draft) + "\n", encoding="utf-8")

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
