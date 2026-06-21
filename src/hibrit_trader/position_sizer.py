"""Kelly / volatilite / seri — dinamik pozisyon boyutu + sermaye dağıtımı."""

from __future__ import annotations

import os

from hibrit_trader.config import GAS_COST_USD, Settings
from hibrit_trader.scanner import Pair


def _recent_streak_multiplier(trades: list, window: int = 5) -> float:
    recent = trades[-window:] if trades else []
    if not recent:
        return 1.0
    wins = sum(1 for t in recent if t.pnl_usd > 0)
    losses = sum(1 for t in recent if t.pnl_usd <= 0)
    if wins >= 3 and losses == 0:
        return 1.25
    if wins >= 2 and losses <= 1:
        return 1.1
    if losses >= 2 and wins == 0:
        return 0.65
    if losses >= 2:
        return 0.8
    return 1.0


def _volatility_multiplier(pair: Pair) -> float:
    vol = abs(pair.chg_h1) + abs(pair.chg_m5) * 0.5
    if vol <= 8:
        return 1.05
    if vol >= 25:
        return 0.7
    if vol >= 18:
        return 0.85
    return 1.0


def _kelly_fraction(trades: list, window: int = 20) -> float:
    """Basit Kelly proxy — son işlemlerden win rate × avg win/loss."""
    recent = trades[-window:] if trades else []
    if len(recent) < 3:
        return 0.5
    wins = [t.pnl_usd for t in recent if t.pnl_usd > 0]
    losses = [abs(t.pnl_usd) for t in recent if t.pnl_usd <= 0]
    if not wins or not losses:
        return 0.5
    p = len(wins) / len(recent)
    avg_w = sum(wins) / len(wins)
    avg_l = sum(losses) / len(losses)
    if avg_l <= 0:
        return 0.5
    b = avg_w / avg_l
    kelly = p - (1 - p) / b
    return max(0.15, min(kelly, 0.85))


def _capital_per_slot(settings: Settings, broker, pair: Pair, max_open: int) -> float:
    """Kalan slotlara nakit dağıt — paper'da tüm sermayeyi kullan."""
    if os.getenv("CAPITAL_DEPLOY_FULL", "1") == "0":
        return settings.max_position_usd
    positions = getattr(broker, "positions", [])
    slots_left = max(1, max_open - len(positions))
    gas = GAS_COST_USD.get(pair.chain, 0.1)
    deployable = max(0.0, broker.balance * settings.capital_deploy_pct - gas * slots_left)
    if deployable <= gas:
        return settings.max_position_usd * 0.5
    per_slot = deployable / slots_left
    return min(per_slot, deployable - gas)


def compute_position_usd(
    settings: Settings,
    broker,
    pair: Pair,
    *,
    max_open: int | None = None,
) -> float:
    if max_open is None:
        max_open = settings.max_open_positions
    base = max(settings.max_position_usd, _capital_per_slot(settings, broker, pair, max_open))
    trades = getattr(broker, "trades", [])
    streak = _recent_streak_multiplier(trades)
    vol = _volatility_multiplier(pair)
    kelly = _kelly_fraction(trades)
    kelly_mult = 0.75 + kelly * 0.5
    size = base * streak * vol * kelly_mult
    lo = settings.max_position_usd * 0.45
    hi = max(settings.max_position_usd * 1.6, base * 1.15)
    return round(max(lo, min(hi, size)), 2)
