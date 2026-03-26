"""記事ドラフトの最低品質を機械的に確認する."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.articles.pipeline import ArticleDraft, CATEGORY_OPTIONS


@dataclass
class ArticleLintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _heading_count(content: str) -> int:
    return len(re.findall(r"(?m)^##\s+", content))


def lint_draft(draft: ArticleDraft) -> ArticleLintResult:
    result = ArticleLintResult()

    if not draft.title or draft.title == "Untitled":
        result.errors.append("タイトルが未設定です")
    elif len(draft.title) > 60:
        result.warnings.append(f"タイトルが長めです: {len(draft.title)}文字")

    if draft.category not in CATEGORY_OPTIONS:
        result.errors.append(f"未定義のカテゴリです: {draft.category}")

    if not draft.tags:
        result.errors.append("タグがありません")
    elif len(draft.tags) < 3:
        result.warnings.append(f"タグが少なめです: {len(draft.tags)}件")
    elif len({tag.lower() for tag in draft.tags}) != len(draft.tags):
        result.warnings.append("タグに重複があります")

    char_count = len(draft.content)
    if char_count < 1200:
        result.errors.append(f"本文が短すぎます: {char_count}文字")
    elif char_count < 1500:
        result.warnings.append(f"本文が推奨下限に届いていません: {char_count}文字")

    headings = _heading_count(draft.content)
    if headings < 3:
        result.errors.append(f"見出しが不足しています: {headings}件")

    if "## まとめ" not in draft.content:
        result.errors.append("まとめ見出しがありません")

    if len(draft.sources) < 2:
        result.errors.append(f"参照元が不足しています: {len(draft.sources)}件")

    low_signal_markers = [
        "(ダイジェストなし)",
        "(分析データなし)",
        "要約する記事本文が提示されていません",
        "記事本文が提供されていない",
    ]
    for marker in low_signal_markers:
        if marker in draft.content:
            result.errors.append(f"低品質なプレースホルダを含んでいます: {marker}")
            break

    if not re.search(r"[0-9０-９]", draft.content):
        result.warnings.append("数字や具体的なデータが少なく、抽象寄りです")

    return result
