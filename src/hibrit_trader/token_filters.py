"""Havuz yaşı / likidite sert filtreleri (Faz 8b)."""

from __future__ import annotations

import os
import time

from hibrit_trader.scanner import Pair


def _min_pool_age_hours() -> float:
    return float(os.getenv("MIN_POOL_AGE_HOURS", "1"))


def _min_liquidity_usd() -> float:
    return float(os.getenv("MIN_LIQUIDITY_USD", "5000"))


def pool_age_hours(pair: Pair) -> float | None:
    if pair.pool_created_at is None:
        return None
    return max(0.0, (time.time() - pair.pool_created_at) / 3600.0)


def token_filter_ok(pair: Pair, *, genesis_ok: bool = False) -> tuple[bool, str]:
    """Sert filtreler — geçmezse giriş yok. Genesis: yaş sınırı yok (0–6h hedef)."""
    min_liq = _min_liquidity_usd()
    if pair.liquidity_usd < min_liq:
        return False, f"likidite düşük (${pair.liquidity_usd:,.0f} < ${min_liq:,.0f})"

    if genesis_ok:
        return True, "genesis · likidite OK"

    min_age = _min_pool_age_hours()
    if min_age <= 0:
        return True, "filtre OK"

    age = pool_age_hours(pair)
    if age is None:
        return True, "havuz yaşı bilinmiyor (atlandı)"
    if age < min_age:
        return False, f"havuz çok yeni ({age:.1f}sa < {min_age:.0f}sa)"
    return True, f"havuz yaşı OK ({age:.1f}sa)"
