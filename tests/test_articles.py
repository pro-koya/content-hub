from __future__ import annotations

import unittest

from src.articles.lint import lint_draft
from src.articles.pipeline import (
    ArticleDraft,
    _build_fallback_draft,
    _parse_digest_sources,
)


SAMPLE_DIGEST = """# Daily Digest - 2026-03-25

## AI Driven Development

### 1. LiteLLM supply chain incident
**出典:** Qiita | [記事リンク](https://qiita.com/example/litellm)
> LiteLLM でサプライチェーン攻撃が起き、GitHub Actions を経由した汚染が問題になった。

**転用示唆:** 本業

### 2. Dify x RAG for internal FAQ
**出典:** Zenn | [記事リンク](https://zenn.dev/example/dify-rag)
> Dify と RAG を使って社内FAQチャットボットを構築する実践記事。検索と生成を組み合わせる運用設計が要点。

**転用示唆:** 個人開発

## Agriculture

### 1. Smart farming update
**出典:** Google News | [記事リンク](https://news.example.com/agri)
> センサーと自動化を組み合わせたスマート農業の導入が進み、現場の判断支援が焦点になっている。
"""


class ArticlePipelineTests(unittest.TestCase):
    def test_parse_digest_sources_skips_low_signal_items(self):
        items = _parse_digest_sources(SAMPLE_DIGEST)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].category, "ai-driven-dev")
        self.assertEqual(items[-1].category, "agriculture")

    def test_fallback_draft_contains_sources_and_summary(self):
        items = _parse_digest_sources(SAMPLE_DIGEST)
        draft = _build_fallback_draft(
            topic="AI駆動開発で最新情報を記事に変える方法",
            category="ai-driven-dev",
            digest_sources=items,
            analysis_report="> **推奨:** `question` が最も高いエンゲージメント",
        )
        self.assertEqual(draft.category, "ai-driven-dev")
        self.assertGreaterEqual(len(draft.sources), 2)
        self.assertIn("## まとめ", draft.content)
        self.assertIn("LiteLLM supply chain incident", draft.content)

    def test_lint_accepts_reasonable_draft(self):
        long_body = (
            "導入として、最新情報を記事に変えるには整理の仕方が重要だと感じている。"
            "ニュースが増えるほど、個別の話題ではなく、共通する変化を見る視点が必要になる。\n\n"
            "## なぜ今このテーマなのか\n"
            "生成AIの更新は早く、1日で複数の変化が重なる。だからこそ、24時間単位で見て共通点をつかむ必要がある。"
            "個別のトピックを追うだけだと、変化の方向ではなく、目立つ話題だけを追ってしまう。"
            "記事にする意味は、散らばったトピックを判断軸に変換するところにある。"
            "たとえば同じ日に出た導入事例とセキュリティ事故を並べるだけでも、運用設計の観点が浮かび上がる。"
            "読み手にとって大事なのは更新件数ではなく、どこから手を付けるべきかが分かることである。\n\n"
            "## 最新情報から見えた変化\n"
            "2026年の運用では、単なる導入事例よりも継続運用の設計が重視されている。"
            "2つの事例を比べると、検索品質と更新フローが成果の差になっていた。"
            "さらにセキュリティ事故の事例を見ると、利便性より先に安全な更新手順を書いておく重要性も増している。"
            "つまり、記事では成功例だけでなく失敗条件まで扱うほうが価値が出る。"
            "数字、障害の起点、再発防止の打ち手が並ぶと、読者は自分の現場に置き換えやすい。"
            "単なる感想ではなく、再現可能な知見として読まれるためには、ここが欠かせない。\n\n"
            "## 記事にするときの切り口\n"
            "記事では、何が起きたかだけでなく、なぜ再現できるのかを書いたほうが価値が出る。"
            "たとえば手元の運用に置き換えて、どの工程から試すかまで書くと読み手が動きやすい。"
            "情報を三つほど並べて共通点を引き出すと、単発の感想ではなく、次に試す判断材料になる。"
            "数字、導入条件、失敗要因の三点を押さえるだけでも、要約の質はかなり変わる。"
            "加えて、自分ならまずどのワークフローを直すかまで書けると、記事は一段具体的になる。"
            "この一文があるだけで、読み手は自分の次の行動を想像しやすくなる。\n\n"
            "## 発信までつなぐ視点\n"
            "Xでは問いから入る発信が伸びていた。記事も同じで、自分の立場が見えると理解されやすい。"
            "読者は完全な正解よりも、なぜその判断に至ったかを知りたがる。"
            "そのため、記事の後半では自分の運用方針や、次の1週間で試すことを明示したほうがよい。"
            "問いから始めて判断軸を示し、最後に小さな実験へ落とし込む流れは、記事でもそのまま機能する。"
            "発信と記事を分断せず、一つの思考の流れとして扱うことが重要になる。\n\n"
            "## まとめ\n"
            "まず3件のトピックを横に並べて、共通点と違いを書き出す。"
            "その上で次の1週間で試すことを決めると、要約で終わらない記事になる。"
            "判断軸と次のアクションが入った瞬間に、情報整理は記事価値へ変わる。"
            "情報収集、解釈、発信、検証の四つがつながったときに、初めて継続的な学びとして回り始める。"
            "最後に、記事の末尾で参照元を明示し、次に試すことを一つ書いておく。"
            "それだけでも読み手の信頼は上がり、書き手自身の検証サイクルも回しやすくなる。"
            "価値のある記事とは、情報量の多さではなく、次の判断に使える形へ整理されている記事のことだ。"
        )
        draft = ArticleDraft(
            title="AI駆動開発の最新情報を記事価値に変える方法",
            slug="ai-driven-dev-review",
            category="ai-driven-dev",
            tags=["AI駆動開発", "情報収集", "ワークフロー設計"],
            sources=["https://example.com/1", "https://example.com/2"],
            content=long_body,
        )
        result = lint_draft(draft)
        self.assertTrue(result.ok, msg=f"errors={result.errors}, warnings={result.warnings}")


if __name__ == "__main__":
    unittest.main()
