"""Slot rotation — max dolu iken en zayıf pozisyonu bırak, güçlü adaya geç."""

from __future__ import annotations

import os

from hibrit_trader.paper import Position


def slot_rotation_enabled() -> bool:
    return os.getenv("SLOT_ROTATION", "1") != "0"


def rotation_min_gap() -> float:
    return float(os.getenv("ROTATION_MIN_SCORE_GAP", "12"))


def rotation_min_confluence() -> float:
    return float(os.getenv("ROTATION_MIN_CONFLUENCE", "55"))


def hold_quality_score(
    pos: Position,
    *,
    dex_score: float,
    unrealized_pnl_pct: float,
) -> float:
    """Açık pozisyon tutma kalitesi — düşük = rotasyon adayı."""
    pnl_term = max(-10.0, min(20.0, unrealized_pnl_pct))
    return round(0.45 * dex_score + 0.35 * pos.entry_score + 0.20 * pnl_term, 1)


def candidate_strength(conf_score: float, dex_score: float) -> float:
    return round(conf_score * 0.55 + dex_score * 0.45, 1)


def pick_weakest_hold(
    positions: list[Position],
    *,
    dex_scores: dict[str, float],
    last_prices: dict[str, float],
) -> tuple[Position, float] | None:
    if not positions:
        return None
    victim: Position | None = None
    weakest = 1e9
    for pos in positions:
        dex = dex_scores.get(pos.pool_address, pos.entry_score * 0.6)
        price = last_prices.get(pos.pool_address, pos.entry_price)
        pnl_pct = 100.0 * (price - pos.entry_price) / max(pos.entry_price, 1e-12)
        hq = hold_quality_score(pos, dex_score=dex, unrealized_pnl_pct=pnl_pct)
        if hq < weakest:
            weakest = hq
            victim = pos
    if victim is None:
        return None
    return victim, weakest


def should_rotate(
    weakest_hold_score: float,
    conf_score: float,
    dex_score: float,
) -> tuple[bool, str]:
    if conf_score < rotation_min_confluence():
        return False, f"konfluans {conf_score:.0f}<{rotation_min_confluence():.0f}"
    strength = candidate_strength(conf_score, dex_score)
    gap = strength - weakest_hold_score
    if gap < rotation_min_gap():
        return False, f"fark yetersiz ({gap:.1f}<{rotation_min_gap():.0f})"
    return True, f"rotate Δ{gap:.1f} (hold {weakest_hold_score:.0f}→{strength:.0f})"
