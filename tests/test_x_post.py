from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.x_post.experiment import enrich_post_record, infer_posting_window
from src.x_post.generator import _parse_generated_text, _select_digest_topics
from src.x_post.lint import parse_output_file


class XPostTests(unittest.TestCase):
    def test_parse_generated_text_keeps_metadata(self):
        text = """# content_hub — 2026-03-26

---

**[question / ja]**
<!-- meta: {"project":"content_hub","content_pillar":"digest_take","target_audience":"AI駆動開発の実務者","source_category":"AI_DRIVEN_DEV","source_topic":"LiteLLM incident","hypothesis":"question hook"} -->
このニュース、実務で一番見るべき点ってどこだと思う？

---
"""
        posts = _parse_generated_text(text)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["content_pillar"], "digest_take")
        self.assertEqual(posts[0]["source_category"], "AI_DRIVEN_DEV")

    def test_parse_output_file_keeps_metadata(self):
        content = """# content_hub — 2026-03-26

---

**[insight / ja]** <!-- posted: 2026-03-26T06:00:00+09:00 -->
<!-- meta: {"project":"content_hub","content_pillar":"question","target_audience":"実務者"} -->
ここが分かれ目。

---
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "content_hub_20260326.md"
            path.write_text(content, encoding="utf-8")
            posts = parse_output_file(path)
        self.assertEqual(posts[0]["posted"], "2026-03-26T06:00:00+09:00")
        self.assertEqual(posts[0]["project"], "content_hub")
        self.assertEqual(posts[0]["target_audience"], "実務者")

    def test_enrich_post_record_preserves_metadata(self):
        record = enrich_post_record({
            "tweet_id": "1",
            "date": "20260326",
            "text": "このニュース、どこを見る？",
            "archetype": "question / ja",
            "project": "content_hub",
            "content_pillar": "digest_take",
            "target_audience": "AI駆動開発の実務者",
            "source_category": "AI_DRIVEN_DEV",
            "source_topic": "LiteLLM incident",
            "prompt_version": "growth-v2",
            "posting_window": "14:30",
        })
        self.assertEqual(record.project, "content_hub")
        self.assertEqual(record.content_pillar, "digest_take")
        self.assertEqual(record.posting_window, "14:30")

    def test_infer_posting_window_accepts_hour_minute(self):
        self.assertEqual(infer_posting_window("14:30"), "afternoon")
        self.assertEqual(infer_posting_window("06:10"), "morning")

    def test_select_digest_topics_respects_focus_order(self):
        topics = [
            {"category": "AGRICULTURE", "title": "A", "summary": "a" * 120, "url": ""},
            {"category": "AI_DRIVEN_DEV", "title": "B", "summary": "b" * 120, "url": ""},
            {"category": "JAPAN_SIGNAL", "title": "C", "summary": "c" * 120, "url": ""},
        ]
        with patch("src.x_post.generator._parse_digest_topics", return_value=topics):
            selected = _select_digest_topics(["AI_DRIVEN_DEV", "JAPAN_SIGNAL"], limit=2)
        self.assertEqual([item["title"] for item in selected], ["B", "C"])


if __name__ == "__main__":
    unittest.main()
