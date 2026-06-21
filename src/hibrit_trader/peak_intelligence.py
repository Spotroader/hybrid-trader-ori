"""Dinamik tepe çıkışı — indikatör + hacim + skor + balina + F&G birleşik karar.

Sabit +18% TP yok; her tick açık pozisyon için tepe yakınlığı skorlanır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from hibrit_trader.cex_confluence import pair_base_symbol
from hibrit_trader.paper import Position
from hibrit_trader.scanner import Pair
from hibrit_trader.trend_stack import compute_trend_stack, dex_trend_metrics


def dynamic_peak_enabled() -> bool:
    return os.getenv("DYNAMIC_PEAK_EXIT", "1") != "0"


@dataclass
class ExitContext:
    dex_score: float = 0.0
    macro_avg: float | None = None
    fear_greed: int | None = None
    exit_bias: str = "neutral"
    whale: dict | None = None


@dataclass
class PeakVerdict:
    score: float
    exit_full: bool
    exit_partial: bool
    sell_fraction: float
    reason: str
    tags: list[str] = field(default_factory=list)


def _vol_spike(pair: Pair) -> float:
    if pair.vol_h1 <= 0:
        return 1.0
    return pair.vol_m5 / max(pair.vol_h1 / 12.0, 1e-9)


def _adaptive_peak_trail_pct(pnl: float) -> float:
    """Kâr arttıkça peak'ten izin verilen geri çekilme daralır."""
    base = float(os.getenv("PEAK_TRAIL_BASE", "8"))
    floor = float(os.getenv("PEAK_TRAIL_FLOOR", "3"))
    return max(floor, base - pnl * 0.015)


def evaluate_peak_intelligence(
    pos: Position,
    pair: Pair,
    pnl: float,
    peak_drawdown_pct: float,
    ctx: ExitContext | None = None,
) -> PeakVerdict | None:
    """0–100 tepe-çıkış skoru; eşik üstü kısmi/tam sat."""
    if not dynamic_peak_enabled():
        return None
    ctx = ctx or ExitContext()
    min_pnl = float(os.getenv("PEAK_INTEL_MIN_PNL", "4"))
    if pnl < min_pnl:
        return None

    pts = 0.0
    tags: list[str] = []

    if pair.chg_m5 <= float(os.getenv("PEAK_EXIT_M5_PCT", "-4")):
        pts += 28
        tags.append(f"5m {pair.chg_m5:+.1f}%")

    if pair.chg_m5 < 0 and pair.chg_h1 > 8:
        pts += 18
        tags.append("h1+/m5−")

    if pair.chg_h24 > 80 and pair.chg_m5 < -3:
        pts += 22
        tags.append("parabolik dönüş")

    spike = _vol_spike(pair)
    if spike < 0.65 and pnl > 15:
        pts += 16
        tags.append("hacim sönüyor")
    elif spike > 2.5 and pair.chg_m5 < -2 and pnl > 20:
        pts += 10
        tags.append("vol spike+red 5m")

    trail_lim = _adaptive_peak_trail_pct(pnl)
    if peak_drawdown_pct >= trail_lim and pair.chg_m5 < 0:
        pts += min(35.0, 18.0 + peak_drawdown_pct * 0.8)
        tags.append(f"peak −{peak_drawdown_pct:.1f}%")

    if ctx.dex_score > 0 and pos.entry_score > 0 and ctx.dex_score < pos.entry_score * 0.72:
        pts += 20
        tags.append(f"skor {ctx.dex_score:.0f}↓")

    if ctx.whale is not None and not ctx.whale.get("buy_signal") and pnl > 12:
        pts += 14
        tags.append("balina AL yok")

    if ctx.fear_greed is not None and ctx.fear_greed >= 72 and pnl > 25:
        pts += 12
        tags.append(f"F&G {ctx.fear_greed}")

    if ctx.exit_bias == "defensive" and pnl > 8:
        pts += 10
        tags.append("Saito def")

    if ctx.macro_avg is not None and ctx.macro_avg < 40 and pnl > 10:
        pts += 8
        tags.append("makro risk-off")

    trend = compute_trend_stack(dex_trend_metrics(pair))
    if not trend.supertrend and pnl > 8:
        pts += 18
        tags.append("ST SAT")
    if trend.whipsaw_risk and pnl > 6:
        pts += 10
        tags.append("whipsaw")

    if not trend.ut_bot and trend.supertrend and pair.chg_m5 < -1.5 and pnl > 15:
        pts += 8
        tags.append("UT kapanış")

    pts = round(min(100.0, pts), 1)
    full_at = float(os.getenv("PEAK_INTEL_FULL", "50"))
    partial_at = float(os.getenv("PEAK_INTEL_PARTIAL", "34"))
    partial_frac = float(os.getenv("PEAK_INTEL_PARTIAL_FRAC", "0.42"))

    exit_full = pts >= full_at
    partial2_at = partial_at + float(os.getenv("PEAK_INTEL_PARTIAL2_BOOST", "8"))
    partial2_frac = float(os.getenv("PEAK_INTEL_PARTIAL2_FRAC", "0.35"))

    exit_partial = False
    sell_fraction = partial_frac
    if exit_full:
        pass
    elif not pos.tp1_done and pts >= partial_at:
        exit_partial = True
    elif pos.tp1_done and not pos.tp2_done and pts >= partial2_at:
        exit_partial = True
        sell_fraction = partial2_frac

    if not exit_full and not exit_partial:
        return None

    reason = "peak intel " + " · ".join(tags[:5])
    return PeakVerdict(
        score=pts,
        exit_full=exit_full,
        exit_partial=exit_partial,
        sell_fraction=1.0 if exit_full else partial_frac,
        reason=reason,
        tags=tags,
    )


def whale_for_pair(pair: Pair | None, whale_rows: list[dict]) -> dict | None:
    if pair is None:
        return None
    sym = pair_base_symbol(pair)
    for row in whale_rows:
        if str(row.get("symbol", "")).upper() == sym:
            return row
    return None
