"""X投稿設定の共有ヘルパー."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "config" / "x_post.json"

DEFAULT_XPOST_CONFIG: dict = {
    "project": "content_hub",
    "default_count": 3,
    "max_chars": 280,
    "max_hashtags": 2,
    "cta_ratio": 0.2,
    "candidate_count": 5,
    "digest_topic_count": 5,
    "focus_categories": [
        "AI_DRIVEN_DEV",
        "JAPAN_SIGNAL",
        "AI_PRODUCT_SAAS",
        "AGRICULTURE",
        "CAREER_HYBRID",
    ],
    "model": "gemini-2.5-flash",
    "dry_run": False,
    "prompt_version": "growth-v2",
}


def load_xpost_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_XPOST_CONFIG.copy()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_XPOST_CONFIG.copy()

    config = DEFAULT_XPOST_CONFIG.copy()
    if isinstance(raw, dict):
        config.update(raw)
    return config


def get_default_project() -> str:
    return str(load_xpost_config().get("project", DEFAULT_XPOST_CONFIG["project"]))
