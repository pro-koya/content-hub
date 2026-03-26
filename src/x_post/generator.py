"""Gemini API を使って当日の X 投稿を生成する."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.x_post.config import get_default_project, load_xpost_config
from src.x_post.lint import (
    _is_cta,
    lint_batch,
    normalize_for_duplicate,
    parse_output_file,
    MAX_POST_LENGTH,
)

ROOT = Path(__file__).resolve().parent.parent.parent
JST = timezone(timedelta(hours=9))

CATEGORY_LABELS = {
    "AI_RESEARCH": "AI Research",
    "AI_PRODUCT_SAAS": "AI Product / SaaS",
    "MACRO_STRUCTURE": "Macro & Structure",
    "JAPAN_SIGNAL": "Japan Signal",
    "AGRICULTURE": "Agriculture",
    "AI_DRIVEN_DEV": "AI Driven Development",
    "CAREER_HYBRID": "Career Hybrid",
    "QIITA_TRENDING": "Qiita Trending",
    "NOTE_TRENDING": "note Trending",
    "X_BUZZ": "X Buzz",
}

LOW_SIGNAL_PATTERNS = (
    "要約する記事本文が提示されていません",
    "記事本文が提供されていない",
    "Comments",
    "(本文なし)",
)

CONTENT_PILLARS = [
    {
        "id": "digest_take",
        "summary": "最新ニュースを一言で翻訳し、なぜ重要かを示す",
    },
    {
        "id": "practical_take",
        "summary": "実務での使い方や導入観点に落とし込む",
    },
    {
        "id": "contrarian",
        "summary": "広まりつつある空気に対して、少し逆張りの視点を出す",
    },
    {
        "id": "question",
        "summary": "実務者の反応を引き出す問いを立てる",
    },
    {
        "id": "career_angle",
        "summary": "キャリアや働き方への示唆につなげる",
    },
]

WEEKDAY_FOCUS = [
    "週の始まりなので、業務改善や優先順位づけに効く投稿を優先する",
    "新機能より運用の変化に注目し、実務者向けに翻訳する",
    "AI駆動開発のニュースから、導入条件や落とし穴を切り出す",
    "日本市場や農業のニュースを、仕事にどう効くかまで落とし込む",
    "今週の重要トピックを比較し、どこを見るべきかを一言で示す",
    "軽めでも価値のある問いを立て、会話が生まれる投稿にする",
    "週の振り返りとして、次週につながる示唆や判断軸を整理する",
]


def _today_str() -> str:
    return datetime.now(JST).strftime("%Y%m%d")


def _today_weekday_ja() -> str:
    w = datetime.now(JST).weekday()
    return ["月", "火", "水", "木", "金", "土", "日"][w]


def _today_theme_hint() -> str:
    return WEEKDAY_FOCUS[datetime.now(JST).weekday()]


def _today_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _load_context_files(project: str) -> dict[str, str]:
    files: dict[str, str] = {}
    project_dir = ROOT / "config" / "projects" / project
    if project_dir.exists():
        for path in sorted(project_dir.glob("*.md")):
            files[f"projects/{project}/{path.name}"] = path.read_text(encoding="utf-8")
    project_template = ROOT / "templates" / f"post_formats_{project}.md"
    templates = project_template if project_template.exists() else ROOT / "templates" / "post_formats.md"
    if templates.exists():
        files[f"templates/{templates.name}"] = templates.read_text(encoding="utf-8")
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        files["CLAUDE.md"] = claude_md.read_text(encoding="utf-8")
    return files


def _load_recent_posts(project: str, days: int = 5) -> str:
    output_dir = ROOT / "output"
    recent_files = sorted(output_dir.glob(f"{project}_*.md"), reverse=True)[:days]
    texts: list[str] = []
    for path in recent_files:
        posts = parse_output_file(path)
        for p in posts:
            meta = p.get("meta", {})
            label = p["archetype"]
            pillar = meta.get("content_pillar", "")
            if pillar:
                label = f"{label} / {pillar}"
            texts.append(f"- [{label}] {p['text']}")
    if texts:
        return "## 直近の投稿（重複を避けること）\n" + "\n".join(texts)
    return ""


def _load_recent_post_texts(project: str, days: int = 5) -> list[str]:
    output_dir = ROOT / "output"
    recent_files = sorted(output_dir.glob(f"{project}_*.md"), reverse=True)[:days]
    out: list[str] = []
    for path in recent_files:
        for p in parse_output_file(path):
            out.append(p["text"])
    return out


def _load_high_performing_posts(project: str, top_n: int = 5) -> str:
    metrics_path = ROOT / "data" / "post_metrics.json"
    if not metrics_path.exists():
        return ""
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    posts = data.get("posts", [])
    if not posts:
        return ""

    filtered = [p for p in posts if (p.get("project") or "liftly") == project]
    if not filtered:
        return ""

    def score(p: dict) -> int:
        s = p.get("engagement_score")
        if s is not None:
            return int(s)
        return int(p.get("like_count", 0) or 0) + int(p.get("retweet_count", 0) or 0) * 2

    sorted_posts = sorted(filtered, key=score, reverse=True)[:top_n]
    lines = [
        "## 過去に伸びた投稿（参考にすること）",
        "以下の投稿はこのプロジェクトで反応が良かったものです。フックや切り口を学習してください。",
        "",
    ]
    for p in sorted_posts:
        text = (p.get("text") or "").strip()
        pillar = p.get("content_pillar") or "unknown"
        if text:
            lines.append(f"- [{pillar}] {text}")
    if len(lines) > 3:
        return "\n".join(lines)
    return ""


def _trim_text(text: str, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    for pattern in LOW_SIGNAL_PATTERNS:
        compact = compact.replace(pattern, "").strip()
    if compact.startswith("はじめに "):
        compact = compact[len("はじめに "):].strip()
    if len(compact) <= limit:
        return compact
    clipped = compact[:limit].rstrip(" 、,")
    last_stop = max(clipped.rfind("。"), clipped.rfind("、"), clipped.rfind("."))
    if last_stop >= 60:
        clipped = clipped[: last_stop + 1]
    return clipped.rstrip() + "…"


def _parse_digest_topics() -> list[dict]:
    digest_path = ROOT / "docs" / "digests" / "latest.md"
    if not digest_path.exists():
        return []

    current_category = ""
    current_item: dict[str, str] | None = None
    summary_lines: list[str] = []
    items: list[dict] = []

    def flush() -> None:
        nonlocal current_item, summary_lines
        if not current_item:
            return
        summary = " ".join(summary_lines).strip()
        if summary and not any(pattern in summary for pattern in LOW_SIGNAL_PATTERNS):
            current_item["summary"] = _trim_text(summary, 180)
            items.append(current_item)
        current_item = None
        summary_lines = []

    for raw_line in digest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            current_category = next((key for key, label in CATEGORY_LABELS.items() if label == heading), heading)
            continue
        if line.startswith("### "):
            flush()
            current_item = {
                "category": current_category,
                "title": re.sub(r"^\d+\.\s*", "", line[4:]).strip(),
                "url": "",
                "source": "",
                "summary": "",
            }
            continue
        if not current_item:
            continue
        if line.startswith("**出典:**"):
            match = re.search(r"\*\*出典:\*\*\s*(.*?)\s*\|\s*\[記事リンク\]\((https?://[^)]+)\)", line)
            if match:
                current_item["source"] = match.group(1).strip()
                current_item["url"] = match.group(2).strip()
            continue
        if line.startswith("> "):
            summary_lines.append(line[2:].strip())

    flush()
    return items


def _select_digest_topics(focus_categories: list[str], limit: int = 5) -> list[dict]:
    topics = _parse_digest_topics()
    if not topics:
        return []

    ranked: list[dict] = []
    for topic in topics:
        category = topic.get("category", "")
        try:
            category_rank = focus_categories.index(category)
        except ValueError:
            category_rank = len(focus_categories) + 1
        score = 100 - category_rank * 10 + min(len(topic.get("summary", "")), 120) / 20
        ranked.append({**topic, "_score": score})

    ranked.sort(key=lambda item: item["_score"], reverse=True)
    return ranked[:limit]


def _format_digest_topics(topics: list[dict]) -> str:
    if not topics:
        return ""
    lines = [
        "## 最新ダイジェストから優先的に扱うトピック",
        "以下のトピックを参考にし、ニュース要約ではなく示唆を出してください。",
        "",
    ]
    for topic in topics:
        category_label = CATEGORY_LABELS.get(topic.get("category", ""), topic.get("category", ""))
        lines.append(f"- [{category_label}] {topic['title']}")
        lines.append(f"  要点: {topic['summary']}")
        if topic.get("url"):
            lines.append(f"  URL: {topic['url']}")
    return "\n".join(lines)


def _pillars_text() -> str:
    lines = ["## 優先するコンテンツピラー"]
    for pillar in CONTENT_PILLARS:
        lines.append(f"- `{pillar['id']}`: {pillar['summary']}")
    return "\n".join(lines)


def _build_prompt(
    count: int,
    max_length: int,
    project: str,
    config: dict,
) -> str:
    context_files = _load_context_files(project)
    recent = _load_recent_posts(project)
    digest_topics = _select_digest_topics(
        focus_categories=list(config.get("focus_categories", [])),
        limit=int(config.get("digest_topic_count", 5)),
    )

    sections: list[str] = []
    sections.append(f"""## あなたの役割

あなたは X 運用担当です。
目的は **フォロワー増加・認知拡大・保存/共有される投稿づくり** です。
単なる宣伝ではなく、「このアカウントをフォローすると実務に効く最新情報が入る」と感じてもらう投稿を作成してください。

### 最重要ルール
- 投稿は **ユーザー価値が先、宣伝は後**
- 1投稿で1メッセージに絞る
- 最新ニュースを使う場合も、要約ではなく「意味」まで翻訳する
- 個人的な感想だけで終わらず、仕事や判断にどう効くかを入れる
- 日本語で書くこと
""")

    sections.append(_pillars_text())

    if digest_topics:
        sections.append(_format_digest_topics(digest_topics))

    for filepath, content in context_files.items():
        sections.append(f"--- {filepath} ---\n{content}")

    if recent:
        sections.append(recent)

    high_performing = _load_high_performing_posts(project)
    if high_performing:
        sections.append(high_performing)

    from src.x_post.experiment import get_prompt_insights

    experiment_insights = get_prompt_insights(project=project)
    if experiment_insights:
        sections.append(experiment_insights)

    prompt_version = config.get("prompt_version", "growth-v2")
    sections.append(f"""## 生成指示

今日は **{_today_iso()}（{_today_weekday_ja()}）** です。
今日の重点: {_today_theme_hint()}
プロジェクト: `{project}`
prompt_version: `{prompt_version}`

### Step 1: 調査
- Google Search を使って、上のダイジェストトピックのうち重要なものを確認する
- 事実関係や論点が薄い場合は無理に使わない
- 最新ニュースが弱い場合は、トレンドから実務に効く問いを作る

### Step 2: 投稿作成
- 投稿案を **{count}本** 作成する
- コンテンツピラーを偏らせない
- 保存・共有・フォローのいずれかにつながる価値を持たせる

#### 絶対ルール
- **{max_length}文字以内**
- ハッシュタグ 0〜2個（末尾）
- CTA は {count}本中最大1本
- 「!」は最大1個
- 絵文字は 0〜2 個
- bans.md の禁止ワードを使わない

#### 出力フォーマット（厳守）

# {project} — {_today_iso()}

---

**[archetype / ja]**
<!-- meta: {{"project":"{project}","content_pillar":"digest_take","target_audience":"AI駆動開発の実務者","source_category":"AI_DRIVEN_DEV","source_topic":"トピック名","hypothesis":"なぜこの投稿が伸びると考えるか","prompt_version":"{prompt_version}"}} -->
投稿本文

---

補足説明は不要です。上記フォーマットのみを出力してください。
""")

    return "\n\n".join(sections)


def _parse_generated_text(text: str) -> list[dict]:
    code_block = re.search(r"```(?:markdown)?\n(.*?)```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)

    blocks = re.split(r"\n---\n", text)
    posts: list[dict] = []

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("# "):
            continue
        match = re.match(r"\*\*\[([^\]]+)\]\*\*", block)
        if not match:
            continue
        archetype = match.group(1).strip()
        lines = block.split("\n")[1:]
        meta: dict = {}
        text_lines = []
        for line in lines:
            meta_match = re.match(r"<!--\s*meta:\s*(\{.*\})\s*-->", line.strip())
            if meta_match:
                try:
                    meta = json.loads(meta_match.group(1))
                except json.JSONDecodeError:
                    meta = {}
                continue
            if line.strip().startswith("> 画像案"):
                break
            text_lines.append(line)
        post_text = "\n".join(text_lines).strip()
        if post_text:
            posts.append({
                "archetype": archetype,
                "text": post_text,
                "meta": meta,
                **meta,
            })

    return posts


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", text))


def _preferred_pillar_penalty(post: dict) -> int:
    pillar = post.get("content_pillar", "")
    if pillar in {"digest_take", "practical_take", "question", "contrarian"}:
        return 0
    return 1


def _select_best_candidate(
    posts: list[dict],
    results: list,
    recent_texts: list[str],
) -> dict:
    def duplicate_score(text: str) -> int:
        norm = normalize_for_duplicate(text)
        prefix = norm[:30] if len(norm) >= 30 else norm
        if not prefix:
            return 0
        cnt = 0
        for recent in recent_texts:
            normalized_recent = normalize_for_duplicate(recent)
            if len(normalized_recent) >= 30 and normalized_recent[:30] == prefix:
                cnt += 1
            elif norm == normalized_recent:
                cnt += 1
        return cnt

    qualified = [(p, r) for p, r in zip(posts, results) if r.ok]
    if not qualified:
        qualified = list(zip(posts, results))

    def score(item: tuple) -> tuple:
        post, lint_result = item
        err_count = len(lint_result.errors)
        warn_count = len(lint_result.warnings)
        cta = 1 if _is_cta(post["text"]) else 0
        dup = duplicate_score(post["text"])
        no_source = 0 if post.get("source_category") else 1
        pillar_penalty = _preferred_pillar_penalty(post)
        return (err_count, warn_count, cta, dup, no_source, pillar_penalty)

    qualified.sort(key=score)
    return qualified[0][0]


def generate(
    count: int = 1,
    dry_run: bool = False,
    max_retries: int = 2,
    project: str | None = None,
) -> list[dict]:
    config = load_xpost_config()
    project_name = project or str(config.get("project", get_default_project()))
    model_name = str(config.get("model", "gemini-2.5-flash"))
    max_length = int(config.get("max_chars", MAX_POST_LENGTH))
    candidate_count = int(config.get("candidate_count", 5))

    internal_count = candidate_count if count == 1 else count
    prompt = _build_prompt(internal_count, max_length=max_length, project=project_name, config=config)

    if dry_run:
        print("=== DRY RUN: プロンプト ===")
        print(prompt[:3000])
        print(f"... (全{len(prompt)}文字)")
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    recent_texts = _load_recent_post_texts(project_name)
    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    for attempt in range(max_retries + 1):
        print(f"生成中... (試行 {attempt + 1}/{max_retries + 1})")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=8192,
                tools=[google_search_tool],
            ),
        )
        generated_text = response.text
        posts = _parse_generated_text(generated_text)
        posts = [post for post in posts if _is_japanese(post["text"])]

        if len(posts) < internal_count:
            print(f"  有効な投稿数不足: {len(posts)}/{internal_count}件", file=sys.stderr)
            if attempt < max_retries:
                continue
            if not posts:
                print("ERROR: 日本語の投稿を1件も取得できませんでした", file=sys.stderr)
                sys.exit(1)

        texts = [post["text"] for post in posts]
        results = lint_batch(
            texts,
            max_length=max_length,
            recent_texts=recent_texts,
            project=project_name,
        )
        qualified = [result for result in results if result.ok]

        if count == 1:
            if not qualified:
                for result in results:
                    for err in result.errors:
                        print(f"  品質NG [{result.post_index}]: {err}", file=sys.stderr)
                if attempt < max_retries:
                    print("  合格が1本もないため再生成します...")
                    continue
                best = _select_best_candidate(posts, results, recent_texts)
                print(f"  ベスト1本を選定（warnings あり）: [{best['archetype']}]")
                return [best]

            best = _select_best_candidate(posts, results, recent_texts)
            print(f"  候補{len(posts)}本からベスト1本を選定: [{best['archetype']}]")
            return [best]

        failed = [result for result in results if not result.ok]
        if not failed:
            print(f"  品質チェック OK: {len(posts)}件")
            return posts

        for result in failed:
            for err in result.errors:
                print(f"  品質NG [{result.post_index}]: {err}", file=sys.stderr)

        if attempt < max_retries:
            print("  再生成します...")
            continue

        ok_posts = [post for post, result in zip(posts, results) if result.ok]
        if ok_posts:
            print(f"  品質チェック通過: {len(ok_posts)}/{len(posts)}件")
            return ok_posts

        print("ERROR: 品質チェックを通過する投稿がありません", file=sys.stderr)
        sys.exit(1)

    return []


def save_output(posts: list[dict], project: str | None = None) -> Path:
    project_name = project or get_default_project()
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{project_name}_{_today_str()}.md"

    lines: list[str] = [f"# {project_name} — {_today_iso()}", ""]

    for post in posts:
        lines.append("---")
        lines.append("")
        lines.append(f"**[{post['archetype']}]**")
        metadata = post.get("meta") or {
            "project": post.get("project", project_name),
            "content_pillar": post.get("content_pillar", ""),
            "target_audience": post.get("target_audience", ""),
            "source_category": post.get("source_category", ""),
            "source_topic": post.get("source_topic", ""),
            "hypothesis": post.get("hypothesis", ""),
            "prompt_version": post.get("prompt_version", ""),
        }
        if any(metadata.values()):
            lines.append(f"<!-- meta: {json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))} -->")
        lines.append(post["text"])
        lines.append("")

    lines.append("---")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"保存完了: {output_path}")
    return output_path
