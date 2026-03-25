"""Gemini API を使って当日の X 投稿を生成する."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google import genai
from google.genai import types

from src.x_post.lint import (
    _is_cta,
    normalize_for_duplicate,
    lint_batch,
    parse_output_file,
    MAX_POST_LENGTH,
)

ROOT = Path(__file__).resolve().parent.parent.parent
JST = timezone(timedelta(hours=9))

CANDIDATES = 5


def _today_str() -> str:
    return datetime.now(JST).strftime("%Y%m%d")


def _today_weekday_ja() -> str:
    w = datetime.now(JST).weekday()
    return ["月", "火", "水", "木", "金", "土", "日"][w]


def _today_theme_hint() -> str:
    w = datetime.now(JST).weekday()
    hints = [
        "筋トレTips・トレーニングの具体策を中心に",
        "個人開発・アプリ開発の話を前面に（筋トレと絡めても可）",
        "哲学×AI・「何を自分で決めるか」といった思想寄りに",
        "筋トレ×AI・記録・振り返りの仕組みの話を",
        "個人開発の裏話・設計の判断など開発者目線を",
        "筋トレあるある・共感ネタ＋トレンドの一言",
        "今週の気づきや体験をラフに（筋トレでも個人開発でも可）",
    ]
    return hints[w]


def _today_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _load_context_files(project: str = "liftly") -> dict[str, str]:
    files: dict[str, str] = {}
    project_dir = ROOT / "config" / "projects" / project
    if project_dir.exists():
        for path in sorted(project_dir.glob("*.md")):
            files[f"projects/{project}/{path.name}"] = path.read_text(encoding="utf-8")
    templates = ROOT / "templates" / "post_formats.md"
    if templates.exists():
        files["templates/post_formats.md"] = templates.read_text(encoding="utf-8")
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        files["CLAUDE.md"] = claude_md.read_text(encoding="utf-8")
    return files


def _load_recent_posts(project: str = "liftly", days: int = 3) -> str:
    output_dir = ROOT / "output"
    recent_files = sorted(output_dir.glob(f"{project}_*.md"), reverse=True)[:days]
    texts: list[str] = []
    for path in recent_files:
        posts = parse_output_file(path)
        for p in posts:
            texts.append(f"- [{p['archetype']}] {p['text']}")
    if texts:
        return "## 直近の投稿（重複を避けること）\n" + "\n".join(texts)
    return ""


def _load_recent_post_texts(project: str = "liftly", days: int = 3) -> list[str]:
    output_dir = ROOT / "output"
    recent_files = sorted(output_dir.glob(f"{project}_*.md"), reverse=True)[:days]
    out: list[str] = []
    for path in recent_files:
        for p in parse_output_file(path):
            out.append(p["text"])
    return out


def _load_high_performing_posts(top_n: int = 5) -> str:
    metrics_path = ROOT / "data" / "post_metrics.json"
    if not metrics_path.exists():
        return ""
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    posts = data.get("posts") or data.get("top_posts") or []
    if not posts:
        return ""

    def score(p: dict) -> int:
        s = p.get("engagement_score")
        if s is not None:
            return int(s)
        return int(p.get("like_count", 0) or 0) + int(p.get("retweet_count", 0) or 0) * 2

    sorted_posts = sorted(posts, key=score, reverse=True)[:top_n]
    lines = [
        "## 過去に伸びた投稿（参考にすること）",
        "以下の投稿はいいね・リポスト数が多かったものです。同じような「刺さり方」を意識して書いてください。",
        "",
    ]
    for p in sorted_posts:
        text = (p.get("text") or p.get("content") or "").strip()
        if text:
            lines.append(f"- {text}")
    if len(lines) > 3:
        return "\n".join(lines)
    return ""


GOOD_EXAMPLES = """## お手本となる投稿例（哲学的だがラフな話し方で統一すること）

例1 [insight / ja]:
やる気がある日にやる、から決まった曜日にやる、に変えただけなんだよね。そしたらなんか質が上がった。結局「いつやるか」を自分で決めてるってことだよね。迷いがなくなるだけでこんなに違うの、おもしろい。

例2 [trend_commentary / ja]:
海外だと「velocity-based training」ってまた流行りだしてるらしい。バーが遅くなったらセット終了、みたいな。日本ではまだあんまり聞かないから、気になる人は英語で検索してみて。数値に頼るか、感覚に頼るか、ってのも結局自分で選んでる話だと思う。

例3 [personal_opinion / ja]:
AI時代に哲学がどう生きるか、ってよく聞かれる。筋トレも同じで、数値化できる部分はAIに任せて、何を大事にするかは自分で決める。そこは代替されないと思う。なんていうか、選ぶほうは人間の仕事だよね。

### お手本の共通点（必ず守ること）
- **全て日本語**で書かれている
- **哲学的だがラフ**
- **漢字よりひらがな多め**
- **「最近の研究」で始めていない**
"""


def _build_prompt(count: int, max_length: int = MAX_POST_LENGTH) -> str:
    context_files = _load_context_files()
    recent = _load_recent_posts()

    sections: list[str] = []

    sections.append(f"""## あなたの役割

あなたは **筋トレが趣味の個人開発者** です。
X（旧Twitter）で筋トレ仲間・個人開発に興味がある人に向けて投稿するコンテンツを作成してください。

### トーンの統一（最重要）— 哲学的だがラフな話し方
- 哲学的 = 問いを立てる、自分なりの解釈や気づきを添える
- ラフ = 敬語にしない、「なんていうか」「〜だよね」「結局」などの話し言葉

### 文体のルール
- **必ず日本語で書くこと**
- 話し言葉＋ゆるい哲学的な気づき
- 1つの投稿で1つのメッセージに絞る

### Bot感を出さない（厳守）
- **「最近の研究」で始める投稿は禁止**
- 書き出しは毎回変える""")

    sections.append(GOOD_EXAMPLES)

    for filepath, content in context_files.items():
        sections.append(f"--- {filepath} ---\n{content}")

    if recent:
        sections.append(recent)

    high_performing = _load_high_performing_posts()
    if high_performing:
        sections.append(high_performing)

    from src.x_post.experiment import get_prompt_insights
    experiment_insights = get_prompt_insights()
    if experiment_insights:
        sections.append(experiment_insights)

    sections.append(f"""## 生成指示

今日は **{_today_iso()}（{_today_weekday_ja()}）** です。
**今日のテーマ:** {_today_theme_hint()}

### Step 1: トレンド調査（Google検索を使うこと）
- Xのハッシュタグ・トレンド動向を把握
- 筋トレの最新情報
- 筋トレ × AI・個人開発

### Step 2: 投稿の作成

投稿案を **{count}本** 作成してください。

#### 絶対ルール
- **日本語で書くこと**
- **{max_length}文字以内（厳守）**
- ハッシュタグ 0〜2個（末尾に配置）
- CTA は {count}本中最大1本
- 「!」は1投稿に最大1個
- 絵文字は1投稿に0〜2個
- bans.md の禁止ワードは使用禁止

#### 出力フォーマット（厳守）

# liftly — {_today_iso()}

---

**[archetype / ja]**
投稿本文

---

上記フォーマットのみを出力してください。
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
        match = re.match(r"\*\*\[([^\]]+)\]\*\*\s*(?:📷\s*)?", block)
        if not match:
            continue
        archetype = match.group(1).strip()
        lines = block.split("\n")[1:]
        text_lines = []
        for line in lines:
            if line.strip().startswith("> 画像案"):
                break
            text_lines.append(line)
        post_text = "\n".join(text_lines).strip()
        if post_text:
            posts.append({"archetype": archetype, "text": post_text})

    return posts


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", text))


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
        for r in recent_texts:
            nr = normalize_for_duplicate(r)
            if len(nr) >= 30 and nr[:30] == prefix:
                cnt += 1
            elif norm == nr:
                cnt += 1
        return cnt

    qualified = [(p, r) for p, r in zip(posts, results) if r.ok]
    if not qualified:
        qualified = list(zip(posts, results))

    def score(item: tuple) -> tuple:
        p, r = item
        err_count = len(r.errors)
        warn_count = len(r.warnings)
        cta = 1 if _is_cta(p["text"]) else 0
        dup = duplicate_score(p["text"])
        return (err_count, warn_count, cta, dup)

    qualified.sort(key=score)
    return qualified[0][0]


def generate(count: int = 1, dry_run: bool = False, max_retries: int = 2) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    config_path = ROOT / "config" / "x_post.json"
    model_name = "gemini-2.5-flash"
    max_length = MAX_POST_LENGTH
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        model_name = config.get("model", model_name)
        max_length = config.get("max_chars", max_length)

    client = genai.Client(api_key=api_key)
    internal_count = CANDIDATES if count == 1 else count
    prompt = _build_prompt(internal_count, max_length=max_length)

    if dry_run:
        print("=== DRY RUN: プロンプト ===")
        print(prompt[:2000])
        print(f"... (全{len(prompt)}文字)")
        return []

    recent_texts = _load_recent_post_texts()
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
        posts = [p for p in posts if _is_japanese(p["text"])]

        if len(posts) < internal_count:
            print(f"  有効な投稿数不足: {len(posts)}/{internal_count}件", file=sys.stderr)
            if attempt < max_retries:
                continue
            if not posts:
                print("ERROR: 日本語の投稿を1件も取得できませんでした", file=sys.stderr)
                sys.exit(1)

        texts = [p["text"] for p in posts]
        results = lint_batch(texts, max_length=max_length, recent_texts=recent_texts)
        qualified = [r for r in results if r.ok]

        if count == 1:
            if not qualified:
                for r in results:
                    for err in r.errors:
                        print(f"  品質NG [{r.post_index}]: {err}", file=sys.stderr)
                if attempt < max_retries:
                    print("  合格が1本もないため再生成します...")
                    continue
                best = _select_best_candidate(posts, results, recent_texts)
                print(f"  ベスト1本を選定（warnings あり）: [{best['archetype']}]")
                return [best]

            best = _select_best_candidate(posts, results, recent_texts)
            print(f"  候補{len(posts)}本からベスト1本を選定: [{best['archetype']}]")
            return [best]

        failed = [r for r in results if not r.ok]
        if not failed:
            print(f"  品質チェック OK: {len(posts)}件")
            return posts

        for r in failed:
            for err in r.errors:
                print(f"  品質NG [{r.post_index}]: {err}", file=sys.stderr)

        if attempt < max_retries:
            print("  再生成します...")
            continue

        ok_posts = [p for p, r in zip(posts, results) if r.ok]
        if ok_posts:
            print(f"  品質チェック通過: {len(ok_posts)}/{len(posts)}件")
            return ok_posts

        print("ERROR: 品質チェックを通過する投稿がありません", file=sys.stderr)
        sys.exit(1)

    return []


def save_output(posts: list[dict], project: str = "liftly") -> Path:
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{project}_{_today_str()}.md"

    lines: list[str] = [f"# {project} — {_today_iso()}", ""]

    for post in posts:
        lines.append("---")
        lines.append("")
        lines.append(f"**[{post['archetype']}]**")
        lines.append(post["text"])
        lines.append("")

    lines.append("---")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"保存完了: {output_path}")
    return output_path
