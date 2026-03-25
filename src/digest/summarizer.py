"""
Article Summarizer
P0: 抽出型要約（頻度ベース）
P1: LLM要約（環境変数 SUMMARIZER=llm で切替）
"""

from __future__ import annotations

import os
import re
from collections import Counter

import requests
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[。．.!?！？])\s*", text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]


def extractive_summarize(text: str, num_sentences: int = 3) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return text[:300] if text else ""

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
        scored.append((i, score, sent))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = sorted(scored[:num_sentences], key=lambda x: x[0])

    return " ".join(t[2] for t in top)


def llm_summarize(text: str, num_sentences: int = 3) -> str:
    api_key = os.environ.get("LLM_API_KEY", "")
    api_url = os.environ.get("LLM_API_URL", "")
    model = os.environ.get("LLM_MODEL", "")

    if not all([api_key, api_url, model]):
        print("[WARN] LLM API 未設定。extractive 要約にフォールバックします。")
        return extractive_summarize(text, num_sentences)

    prompt = (
        f"以下の記事を{num_sentences}文以内で**必ず日本語で**要約してください。"
        f"英語の記事であっても日本語に翻訳して要約してください。"
        f"事実のみを簡潔に述べ、洞察や意見は含めないでください。"
        f"要約のみを出力し、前置きや説明は不要です。\n\n"
        f"{text[:3000]}"
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
                "max_tokens": 500,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            print(f"[WARN] LLM API error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[WARN] LLM API 呼び出し失敗: {e}。extractive にフォールバック。")

    return extractive_summarize(text, num_sentences)


def summarize(html_content: str, method: str = "extractive", num_sentences: int = 3) -> str:
    text = html_to_text(html_content)
    if not text:
        return "(本文なし)"

    if method == "llm":
        return llm_summarize(text, num_sentences)
    return extractive_summarize(text, num_sentences)
