"""
Article Summarizer
- LLM (Gemini) が利用可能な場合: 日本語で詳細な要約を生成
- LLM 未設定の場合: 抽出型要約にフォールバック（文数を増やして詳細化）
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _is_mostly_english(text: str) -> bool:
    """テキストが主に英語かどうかを判定する。"""
    if not text:
        return False
    ascii_count = sum(1 for c in text if c.isascii() and c.isalpha())
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return False
    return (ascii_count / total_alpha) > 0.7


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[。．.!?！？])\s*", text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]


def extractive_summarize(text: str, num_sentences: int = 5) -> str:
    """抽出型要約。頻出語ベースでスコアリングし、重要文を抽出する。"""
    sentences = split_sentences(text)
    if not sentences:
        return text[:500] if text else ""

    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    words = re.findall(r"\w{2,}", text.lower())
    word_freq = Counter(words)

    if word_freq:
        threshold = max(word_freq.values()) * 0.95
        word_freq = Counter({w: f for w, f in word_freq.items() if f < threshold})

    scored = []
    for i, sent in enumerate(sentences):
        sent_words = re.findall(r"\w{2,}", sent.lower())
        if not sent_words:
            score = 0.0
        else:
            score = sum(word_freq.get(w, 0) for w in sent_words) / len(sent_words)
        if i == 0:
            score *= 1.5
        if i == 1:
            score *= 1.2
        scored.append((i, score, sent))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = sorted(scored[:num_sentences], key=lambda x: x[0])

    summary = " ".join(t[2] for t in top)

    if _is_mostly_english(text):
        summary = f"[英語記事] {summary}"

    return summary


def _gemini_summarize(text: str, num_sentences: int = 5) -> str | None:
    """Google Gemini API（google-genai パッケージ）で要約する。"""
    api_key = os.environ.get("LLM_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")

        prompt = (
            f"以下の記事を日本語で{num_sentences}文程度で要約してください。\n\n"
            f"## 要約のルール\n"
            f"- 英語の記事であっても、必ず日本語に翻訳して要約すること\n"
            f"- 記事の主要なポイント、具体的なデータや数値、影響範囲を含めること\n"
            f"- 技術用語は正確に記載し、必要に応じて補足説明を加えること\n"
            f"- 「この記事は～」のような前置きは不要。要約本文のみ出力すること\n"
            f"- 読者が記事を読まなくても概要が把握できるレベルの詳細さにすること\n\n"
            f"## 記事本文\n{text[:4000]}"
        )

        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
    except ImportError:
        pass
    except Exception as e:
        print(f"  [WARN] Gemini API error: {e}")

    return None


def _openai_compatible_summarize(text: str, num_sentences: int = 5) -> str | None:
    """OpenAI 互換 API で要約する（フォールバック）。"""
    import requests

    api_key = os.environ.get("LLM_API_KEY", "")
    api_url = os.environ.get("LLM_API_URL", "")
    model = os.environ.get("LLM_MODEL", "")

    if not all([api_key, api_url, model]):
        return None

    prompt = (
        f"以下の記事を日本語で{num_sentences}文程度で要約してください。\n\n"
        f"## 要約のルール\n"
        f"- 英語の記事であっても、必ず日本語に翻訳して要約すること\n"
        f"- 記事の主要なポイント、具体的なデータや数値、影響範囲を含めること\n"
        f"- 技術用語は正確に記載し、必要に応じて補足説明を加えること\n"
        f"- 「この記事は～」のような前置きは不要。要約本文のみ出力すること\n"
        f"- 読者が記事を読まなくても概要が把握できるレベルの詳細さにすること\n\n"
        f"## 記事本文\n{text[:4000]}"
    )

    try:
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            print(f"  [WARN] LLM API error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [WARN] LLM API error: {e}")

    return None


def summarize(html_content: str, method: str = "auto", num_sentences: int = 5) -> str:
    """記事を日本語で要約する。

    method:
      - "auto": LLM が使えれば LLM、なければ extractive（デフォルト）
      - "llm": LLM を使用（失敗時は extractive にフォールバック）
      - "extractive": 抽出型要約のみ
    """
    text = html_to_text(html_content)
    if not text:
        return "(本文なし)"

    if method in ("auto", "llm"):
        result = _gemini_summarize(text, num_sentences)
        if result:
            return result

        result = _openai_compatible_summarize(text, num_sentences)
        if result:
            return result

        if method == "auto":
            return extractive_summarize(text, num_sentences)
        else:
            print("  [WARN] LLM API 未設定。extractive 要約にフォールバックします。")
            return extractive_summarize(text, num_sentences)

    return extractive_summarize(text, num_sentences)
