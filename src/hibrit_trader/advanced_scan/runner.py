"""Gelişmiş tarama orkestrasyonu — mod birleştirme + tam isabet."""

from __future__ import annotations

from hibrit_trader.advanced_scan.cex_scan import scan_cex
from hibrit_trader.advanced_scan.derivatives import scan_derivatives
from hibrit_trader.advanced_scan.grid_hint import grid_hints
from hibrit_trader.advanced_scan.news_scan import scan_news
from hibrit_trader.advanced_scan.social import social_status
from hibrit_trader.advanced_scan.whale_proxy import scan_whale_proxy

VALID_MODES = frozenset({"cex", "news", "whale", "derivatives", "grid", "social"})

MODE_LABELS = {
    "cex": "Binance/OKX Teknik",
    "news": "Haber + Balina",
    "whale": "Balina hareketi",
    "derivatives": "Funding/OI Konfluans",
    "grid": "Dinamik Spot Grid",
    "social": "X / Sosyal (RED)",
}


def list_modes() -> list[dict]:
    social = social_status()
    return [
        {
            "id": mid,
            "label": MODE_LABELS[mid],
            "enabled": mid != "social",
            "note": social["reason"] if mid == "social" else None,
        }
        for mid in ("cex", "news", "whale", "derivatives", "grid", "social")
    ]


def _merge_scores(parts: list[float]) -> float:
    if not parts:
        return 0.0
    return round(sum(parts) / len(parts), 1)


def run_advanced_scan(modes: list[str], limit: int = 15) -> dict:
    active = [m for m in modes if m in VALID_MODES and m != "social"]
    if not active:
        active = ["cex"]

    cex_rows: list[dict] = []
    news_map: dict = {}
    whale_map: dict = {}
    deriv_map: dict = {}
    grid_map: dict = {}

    if "cex" in active:
        cex_rows = scan_cex(limit=limit)
    symbols = [r["symbol"] for r in cex_rows] if cex_rows else []

    if "news" in active:
        news_map = scan_news(limit=30)
        if not symbols:
            symbols = list(news_map.keys())[:limit]

    if "whale" in active:
        whale_map = scan_whale_proxy(symbols or list(news_map.keys())[:limit])

    if "derivatives" in active:
        deriv_map = scan_derivatives(symbols or list(news_map.keys())[:limit])

    if "grid" in active:
        grid_map = grid_hints(symbols or list(news_map.keys())[:limit])

    # Birleşik satırlar
    all_syms = set(symbols) | set(news_map) | set(whale_map) | set(deriv_map)
    rows: list[dict] = []
    for sym in all_syms:
        cex = next((r for r in cex_rows if r["symbol"] == sym), None)
        news = news_map.get(sym)
        whale = whale_map.get(sym)
        deriv = deriv_map.get(sym)
        grid = grid_map.get(sym)

        parts: list[float] = []
        reasons: list[str] = []
        if cex:
            parts.append(cex["score"])
            reasons.append(f"Teknik {cex['score']}: {cex['reason']}")
        if news:
            parts.append(news["score"])
            reasons.append(f"Haber: {news.get('headline', '')[:60]}")
        if whale and "whale" in active:
            parts.append(whale["score"])
            reasons.append(whale["reason"])
        if deriv and "derivatives" in active:
            parts.append(deriv["score"])
            reasons.append(f"Türev {deriv['score']}: {deriv['reason']}")
        if grid and "grid" in active:
            parts.append(grid["score"])
            reasons.append(grid["reason"])

        composite = _merge_scores(parts) if parts else 0.0
        layers = sum(1 for x in (cex, news if "news" in active else None, whale if "whale" in active else None, deriv if "derivatives" in active else None) if x)
        tam = (
            composite >= 55
            and layers >= 2
            and (deriv is None or deriv["score"] >= 40)
            and (cex is None or cex["score"] >= 50)
        )
        if composite < 30 and not tam:
            continue

        rows.append({
            "symbol": sym,
            "exchange": cex["exchange"] if cex else "—",
            "score": composite,
            "tam_isabet": tam,
            "reason": " · ".join(reasons[:3]),
            "cex_score": cex["score"] if cex else None,
            "news_score": news["score"] if news else None,
            "whale_score": whale["score"] if whale else None,
            "deriv_score": deriv["score"] if deriv else None,
            "grid_hint": grid["reason"] if grid else None,
        })

    rows.sort(key=lambda r: (-int(r["tam_isabet"]), -r["score"]))
    return {
        "modes": active,
        "social": social_status(),
        "count": len(rows),
        "results": rows[:limit],
    }
