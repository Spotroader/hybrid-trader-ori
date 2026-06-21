"""Balina proxy — borsa hacim anomalisi (on-chain whale Faz 5a tam sürüm)."""

from __future__ import annotations

import httpx


def scan_whale_proxy(symbols: list[str]) -> dict[str, dict]:
    """Yüksek hacim spike = balina ilgisi proxy skoru."""
    out: dict[str, dict] = {}
    if not symbols:
        return out
    with httpx.Client() as client:
        try:
            r = client.get("https://api.binance.com/api/v3/ticker/24hr", timeout=12)
            r.raise_for_status()
            tickers = {t["symbol"]: t for t in r.json()}
        except Exception:
            return out
        for base in symbols:
            sym = f"{base}USDT"
            t = tickers.get(sym)
            if not t:
                continue
            vol = float(t.get("quoteVolume", 0))
            count = int(t.get("count", 0))
            chg = float(t.get("priceChangePercent", 0))
            score = min(100, 40 + (vol / 50_000_000) * 20 + min(count / 100_000, 1) * 20)
            if chg > 0:
                score += min(chg, 10) * 2
            out[base] = {
                "score": round(min(score, 100), 1),
                "reason": f"24s hacim ${vol/1e6:.0f}M · işlem {count} · balina proxy",
            }
    return out
