"""品質チェックモジュール — 投稿の絶対ルールを機械的に検証する."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.x_post.config import get_default_project

ROOT = Path(__file__).resolve().parent.parent.parent

MAX_POST_LENGTH = 280
CTA_PHRASES = [
    "プロフィールのリンクからどうぞ",
    "プロフのリンクから",
    "iOS / Android 無料です",
    "iOS/Android 無料です",
    "気になったらプロフのリンクから",
    "フォローしておいて",
    "フォローで",
    "必要ならフォロー",
]

EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\u2702-\u27b0"
    "\u200d"
    "\ufe0f"
    "]+",
    flags=re.UNICODE,
)


def _bans_path(project: str) -> Path:
    return ROOT / "config" / "projects" / project / "bans.md"


def _load_banned_words(project: str | None = None) -> list[str]:
    project_name = project or get_default_project()
    bans_path = _bans_path(project_name)
    if not bans_path.exists():
        return []
    words: list[str] = []
    for line in bans_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- "):
            word = line[2:].strip()
            if word:
                words.append(word)
    return words


@dataclass
class LintResult:
    post_index: int
    text: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def _count_hashtags(text: str) -> int:
    return len(re.findall(r"#\S+", text))


def _count_exclamation(text: str) -> int:
    return text.count("!") + text.count("！")


def _count_emoji(text: str) -> int:
    return len(EMOJI_RE.findall(text))


def _is_cta(text: str) -> bool:
    return any(phrase in text for phrase in CTA_PHRASES)


CTA_PROMO_RE = re.compile(
    r"DL|ダウンロード|インストール|App\s*Store|ストア|リンク|入れてみて|使ってみて|無料で(?:入手|試)|フォロー"
)

BOT_OPENING_RE = re.compile(
    r"^(最近の研究|研究によると|調査では|最近の研究で|研究では|データによると)"
)


def _has_specificity(text: str) -> bool:
    if re.search(r"[0-9０-９]", text):
        return True
    action_phrases = ["してみて", "やってみて", "試してみて", "すると", "だけ"]
    if any(p in text for p in action_phrases):
        return True
    if "たとえば" in text or "例えば" in text:
        return True
    return False


def normalize_for_duplicate(text: str) -> str:
    s = re.sub(r"[^\w\s]", "", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def lint_post(
    text: str,
    index: int = 0,
    max_length: int | None = None,
    recent_texts: list[str] | None = None,
    project: str | None = None,
) -> LintResult:
    result = LintResult(post_index=index, text=text)
    limit = max_length if max_length is not None else MAX_POST_LENGTH
    banned_words = _load_banned_words(project)

    char_count = len(text)
    if char_count > limit:
        result.errors.append(f"文字数超過: {char_count}/{limit}")

    hashtag_count = _count_hashtags(text)
    if hashtag_count > 2:
        result.errors.append(f"ハッシュタグ超過: {hashtag_count}/2")

    excl_count = _count_exclamation(text)
    if excl_count > 1:
        result.errors.append(f"感嘆符超過: {excl_count}/1")

    emoji_count = _count_emoji(text)
    if emoji_count > 2:
        result.errors.append(f"絵文字超過: {emoji_count}/2")

    text_lower = text.lower()
    for word in banned_words:
        if word.lower() in text_lower:
            result.errors.append(f"禁止ワード検出: '{word}'")

    if not _has_specificity(text):
        result.warnings.append("具体性が薄い: 数字/行動/例示がありません")

    if CTA_PROMO_RE.search(text):
        result.warnings.append("CTA/宣伝臭の可能性: 強い誘導語を検出")

    if BOT_OPENING_RE.search(text.strip()):
        result.warnings.append("Bot感: 「最近の研究」等の書き出しは避ける")

    if recent_texts:
        norm_curr = normalize_for_duplicate(text)
        for r in recent_texts:
            norm_r = normalize_for_duplicate(r)
            if norm_curr == norm_r:
                result.warnings.append("直近投稿との近似重複の可能性")
                break
            if len(norm_curr) >= 30 and len(norm_r) >= 30 and norm_curr[:30] == norm_r[:30]:
                result.warnings.append("直近投稿との近似重複の可能性")
                break

    return result


def lint_batch(
    posts: list[str],
    max_length: int | None = None,
    recent_texts: list[str] | None = None,
    project: str | None = None,
) -> list[LintResult]:
    results = [
        lint_post(text, i, max_length=max_length, recent_texts=recent_texts, project=project)
        for i, text in enumerate(posts)
    ]

    cta_count = sum(1 for text in posts if _is_cta(text))
    max_cta = max(1, len(posts) // 5)
    if cta_count > max_cta:
        for r in results:
            if _is_cta(r.text):
                r.errors.append(
                    f"CTA比率超過: {cta_count}件 (最大{max_cta}件/{len(posts)}件中)"
                )

    for i in range(len(posts) - 1):
        if _is_cta(posts[i]) and _is_cta(posts[i + 1]):
            results[i + 1].errors.append("CTAが連続しています")

    return results


def parse_output_file(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", content)
    posts: list[dict] = []

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("# "):
            continue

        match = re.match(
            r"\*\*\[([^\]]+)\]\*\*\s*(?:📷\s*)?(?:<!--\s*posted:\s*(.+?)\s*-->)?",
            block,
        )
        if not match:
            continue

        archetype = match.group(1).strip()
        posted = match.group(2)

        lines = block.split("\n")
        metadata: dict = {}
        text_lines: list[str] = []
        for line in lines[1:]:
            if line.strip().startswith("> 画像案"):
                break
            meta_match = re.match(r"<!--\s*meta:\s*(\{.*\})\s*-->", line.strip())
            if meta_match:
                try:
                    metadata = json.loads(meta_match.group(1))
                except json.JSONDecodeError:
                    metadata = {}
                continue
            text_lines.append(line)

        text = "\n".join(text_lines).strip()
        if text:
            posts.append({
                "archetype": archetype,
                "text": text,
                "posted": posted,
                "meta": metadata,
                **metadata,
            })

    return posts
