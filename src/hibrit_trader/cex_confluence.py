"""CEX tut listesi ↔ DEX trending havuz eşlemesi (Faz 8)."""

from __future__ import annotations

import re

from hibrit_trader.scanner import Pair

_SYMBOL_RE = re.compile(r"^([A-Za-z0-9]+)")


def pair_base_symbol(pair: Pair) -> str:
    """CARDS / USDC 0.01% → CARDS"""
    left = pair.name.split("/")[0].strip()
    m = _SYMBOL_RE.match(left)
    return (m.group(1) if m else left).upper()


def cex_symbol_scores(binance_holds: list[dict], okx_holds: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in binance_holds + okx_holds:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        score = float(row.get("score", 0))
        out[sym] = max(out.get(sym, 0.0), score)
    return out


def cex_boost_points(pair: Pair, cex_scores: dict[str, float] | None) -> tuple[float, str | None]:
    """Binance/OKX tut skoruna göre DEX skor bonusu."""
    if not cex_scores:
        return 0.0, None
    sym = pair_base_symbol(pair)
    hold = cex_scores.get(sym, 0.0)
    if hold >= 70:
        return 12.0, sym
    if hold >= 55:
        return 8.0, sym
    if hold >= 45:
        return 4.0, sym
    return 0.0, sym if sym in cex_scores else None


def cex_hold_score(pair: Pair, cex_scores: dict[str, float] | None) -> float:
    if not cex_scores:
        return 0.0
    return cex_scores.get(pair_base_symbol(pair), 0.0)
