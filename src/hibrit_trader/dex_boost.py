"""Dexscreener ⚡ boost — giriş skoru ayarı.

Founder kuralı: ⚡500 = geç pump (bonus değil ceza); erken ⚡ (10–100) tercih.
"""

from __future__ import annotations

from hibrit_trader.dex_trending_strategy import pool_age_hours
from hibrit_trader.early_launch import classify_pump_window
from hibrit_trader.scanner import Pair

_WINDOW_SORT = {
    "genesis": 0,
    "early": 1,
    "standard": 2,
    "trending_late": 9,
}


def dex_boost_entry_adjustment(boost_score: int) -> float:
    """Watchlist/rank giriş skoruna eklenecek delta."""
    bs = int(boost_score or 0)
    if bs >= 500:
        return -12.0
    if bs >= 100:
        return 2.0
    if bs >= 10:
        return 8.0
    if bs > 0:
        return 5.0
    return 0.0


def watchlist_sort_key(score: float, pair: Pair) -> tuple:
    """Panel watchlist sırası — genesis üstte; trending_late (Chaton sınıfı) altta."""
    pw = classify_pump_window(pair)
    boost = int(getattr(pair, "boost_score", 0) or 0)
    age = pool_age_hours(pair)
    young = age is not None and age <= 6
    early_boost = 10 <= boost < 100
    return (
        _WINDOW_SORT.get(pw["window"], 2),
        1 if boost >= 500 else 0,
        0 if young else 1,
        0 if early_boost else (2 if boost >= 500 else 1),
        -float(score),
    )
