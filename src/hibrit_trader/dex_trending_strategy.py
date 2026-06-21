"""Dexscreener Trending 6H mantığı — boost, hacim/likidite, txns, momentum, dump filtresi.

Paper agresif modda birincil giriş yolu: CEX Supertrend yerine DS trending sinyali.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from hibrit_trader.scanner import Pair


def trending_fast_enabled() -> bool:
    return os.getenv("DEX_TRENDING_FAST", "1") != "0"


def _dump_threshold_pct() -> float:
    return float(os.getenv("TRENDING_DUMP_M5_PCT", "-10"))


def _min_turnover() -> float:
    """Vol24h / liq — Dex'te sıcak çiftler genelde 5–80x."""
    return float(os.getenv("TRENDING_MIN_TURNOVER", "4"))


@dataclass
class TrendingSignal:
    score: float
    entry_ok: bool
    reason: str
    dump_risk: bool = False
    turnover: float = 0.0


def pool_age_hours(pair: Pair) -> float | None:
    if pair.pool_created_at is None:
        return None
    return max(0.0, (time.time() - pair.pool_created_at) / 3600.0)


def trending_score(pair: Pair) -> float:
    """0..100 — Dexscreener trending 6H benzeri sıralama skoru."""
    liq = max(pair.liquidity_usd, 1.0)
    vol = max(pair.vol_h24, 1.0)
    turnover = vol / liq
    boost = int(getattr(pair, "boost_score", 0) or 0)
    txns = int(getattr(pair, "txns_h24", 0) or pair.txns_h1 or 0)

    boost_pts = min(25.0, boost / 20.0) if boost else 0.0
    turn_pts = min(30.0, turnover * 2.5)
    txn_pts = min(15.0, txns / 8000.0)

    mom = max(pair.chg_h1, 0.0) * 0.35 + max(pair.chg_m5, 0.0) * 0.8
    mom += min(max(pair.chg_h24, 0.0) * 0.04, 12.0)
    if pair.chg_m5 < 0:
        mom += max(pair.chg_m5 * 0.5, -8.0)
    mom_pts = min(20.0, max(0.0, mom))

    liq_pts = min(10.0, (pair.liquidity_usd / 80_000.0) * 10.0)

    age = pool_age_hours(pair)
    age_pts = 0.0
    if age is not None:
        if age <= 24:
            age_pts = min(10.0, 10.0 - age * 0.25)
        elif age <= 72:
            age_pts = 4.0

    return round(min(100.0, boost_pts + turn_pts + txn_pts + mom_pts + liq_pts + age_pts), 1)


def evaluate_trending(pair: Pair) -> TrendingSignal:
    """Giriş sinyali — dump bıçağından kaçın, sıcak trending çiftleri yakala."""
    liq = pair.liquidity_usd
    min_liq = float(os.getenv("TRENDING_MIN_LIQ_USD", "12000"))
    if liq < min_liq or pair.price_usd <= 0:
        return TrendingSignal(0.0, False, f"likidite < ${min_liq:,.0f}", False, 0.0)

    turnover = pair.vol_h24 / max(liq, 1.0)
    boost = int(getattr(pair, "boost_score", 0) or 0)
    dump_lim = _dump_threshold_pct()
    score = trending_score(pair)

    if pair.chg_m5 <= dump_lim:
        return TrendingSignal(
            score, False, f"5m dump %{pair.chg_m5:.1f} (limit {dump_lim:.0f})", True, turnover
        )

    if pair.chg_h24 > 800 and pair.chg_m5 < -5:
        return TrendingSignal(score, False, "parabolik — 5m çöküş", True, turnover)

    hot = boost >= 50 or turnover >= _min_turnover()
    if not hot:
        return TrendingSignal(score, False, f"sıcak değil (boost {boost}, turn {turnover:.1f}x)", False, turnover)

    momentum_ok = (
        pair.chg_m5 > 0
        or (pair.chg_h1 > 0 and pair.chg_m5 > dump_lim / 2)
        or (pair.chg_h24 > 25 and pair.chg_m5 > -4 and pair.chg_h1 > -5)
        or (
            pair.chg_h24 > 150
            and turnover >= _min_turnover() * 1.5
            and pair.chg_h1 > -12
            and pair.chg_m5 > max(dump_lim / 2, -8)
        )
    )
    if not momentum_ok:
        return TrendingSignal(score, False, "momentum yok (h1/m5)", False, turnover)

    entry_ok = score >= float(os.getenv("TRENDING_ENTRY_MIN", "42"))
    reason = f"DS trending {score:.0f} · ⚡{boost} · {turnover:.0f}x vol/liq"
    return TrendingSignal(score, entry_ok, reason, False, turnover)
