"""Haber + sentiment — ücretsiz aggregator."""

from __future__ import annotations

import re

import httpx

NEWS_URLS = (
    "https://cryptocurrency.cv/api/trending",
    "https://cryptocurrency.cv/api/news",
)


def _symbol_from_text(text: str) -> set[str]:
    found = set(re.findall(r"\b([A-Z]{2,10})\b", text.upper()))
    noise = {"USD", "USDT", "BTC", "ETH", "THE", "FOR", "AND", "API", "CEO", "ETF", "SEC"}
    return {s for s in found if s not in noise and len(s) <= 6}


def scan_news(limit: int = 20) -> dict[str, dict]:
    """Sembol -> haber skoru ve özet."""
    by_symbol: dict[str, dict] = {}
    with httpx.Client() as client:
        payload = None
        for url in NEWS_URLS:
            try:
                r = client.get(url, params={"limit": 30, "hours": 24}, timeout=12)
                if r.status_code == 200:
                    payload = r.json()
                    break
            except Exception:
                continue
        if payload is None:
            return {}

        articles = []
        if isinstance(payload, dict):
            if "topics" in payload:
                for t in payload.get("topics", []):
                    name = t.get("topic") or t.get("name") or ""
                    sent = t.get("sentiment") or t.get("score") or "neutral"
                    articles.append({"title": name, "sentiment": sent})
            elif "articles" in payload:
                articles = payload["articles"]
            elif "data" in payload:
                articles = payload["data"]
        elif isinstance(payload, list):
            articles = payload

        for art in articles[:40]:
            if not isinstance(art, dict):
                continue
            title = art.get("title") or art.get("topic") or art.get("name") or ""
            sent_raw = str(art.get("sentiment", "neutral")).lower()
            if "bull" in sent_raw or "positive" in sent_raw:
                sent_score = 75
            elif "bear" in sent_raw or "negative" in sent_raw:
                sent_score = 25
            else:
                sent_score = 50
            for sym in _symbol_from_text(title):
                prev = by_symbol.get(sym)
                if not prev or sent_score > prev["score"]:
                    by_symbol[sym] = {
                        "score": float(sent_score),
                        "headline": title[:120],
                        "sentiment": sent_raw,
                    }
    return dict(list(by_symbol.items())[:limit])
