"""7–8x pump profili — yaş, hacim/likidite, txns, cüzdan, boost, momentum.

Dexscreener trending'deki XP/TRUAMP tipi çiftleri skorlar; giriş konfluansı ve watchlist zenginleştirmesi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hibrit_trader.dex_trending_strategy import pool_age_hours, trending_score
from hibrit_trader.scanner import Pair


@dataclass
class PumpProfile:
    moonshot_score: float
    wallet_count: int
    whale_signal: bool
    turnover: float
    age_hours: float | None
    trend_score: float
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        tag = "🎯" if self.moonshot_score >= 62 else ("🔥" if self.moonshot_score >= 48 else "")
        return {
            "moonshot_score": round(self.moonshot_score, 1),
            "wallet_count": self.wallet_count,
            "whale_signal": self.whale_signal,
            "turnover": round(self.turnover, 1),
            "age_hours": round(self.age_hours, 1) if self.age_hours is not None else None,
            "trend_score": round(self.trend_score, 1),
            "signals": self.signals[:4],
            "moon_tag": tag,
        }


def _turnover(pair: Pair) -> float:
    return pair.vol_h24 / max(pair.liquidity_usd, 1.0)


def analyze_pump_pair(
    pair: Pair,
    *,
    wallet_count: int = 0,
    whale_row: dict | None = None,
) -> PumpProfile:
    """0..100 moonshot skoru — yüksek h24 + sıcak turnover + genç havuz."""
    liq = max(pair.liquidity_usd, 1.0)
    turnover = _turnover(pair)
    age = pool_age_hours(pair)
    boost = int(getattr(pair, "boost_score", 0) or 0)
    txns = int(getattr(pair, "txns_h24", 0) or pair.txns_h1 or 0)
    whale_buy = bool(whale_row.get("buy_signal")) if whale_row else False
    if whale_row:
        wallet_count = max(wallet_count, int(whale_row.get("wallet_count", 0)))

    score = 0.0
    signals: list[str] = []

    if turnover >= 8:
        score += min(28.0, turnover * 1.8)
        signals.append(f"turn {turnover:.0f}x")
    if age is not None and age <= 48:
        score += min(22.0, 22.0 - age * 0.35)
        signals.append(f"age {age:.0f}h")
        if age <= 6:
            score += min(12.0, 12.0 - age * 1.2)
            signals.append("genç")
    if txns >= 8000:
        score += min(18.0, txns / 2500.0)
        signals.append(f"txns {txns // 1000}k")
    if boost >= 500:
        score -= 15.0
        signals.append("⚡500 geç")
    elif boost >= 10:
        score += min(12.0, boost / 30.0)
        signals.append(f"⚡{boost}")
    if pair.chg_h24 >= 120:
        score += min(20.0, pair.chg_h24 * 0.025)
        signals.append(f"h24 +{pair.chg_h24:.0f}%")
    if pair.chg_h1 > 0 and pair.chg_m5 > -8:
        score += min(12.0, pair.chg_h1 * 0.15 + max(pair.chg_m5, 0) * 0.5)
    if wallet_count >= 2:
        score += min(12.0, wallet_count * 2.5)
        signals.append(f"{wallet_count} cüzdan")
    if whale_buy:
        score += 18.0
        signals.append("balina AL")

    ts = trending_score(pair)
    score = min(100.0, score * 0.75 + ts * 0.25)

    return PumpProfile(
        moonshot_score=round(score, 1),
        wallet_count=wallet_count,
        whale_signal=whale_buy,
        turnover=turnover,
        age_hours=age,
        trend_score=ts,
        signals=signals,
    )


def moonshot_entry_relax() -> float:
    import os

    return float(os.getenv("MOONSHOT_CONFLUENCE_RELAX", "10"))


def moonshot_min_score() -> float:
    import os

    return float(os.getenv("MOONSHOT_MIN_SCORE", "62"))


def founder_fast_entry_ok(pair: Pair, pump: PumpProfile) -> bool:
    """Genç + 🐋 + h1>0 + ⚡<100 — erken pump giriş hızlandırıcı."""
    import os

    if os.getenv("FOUNDER_FAST_PATH", "1") == "0":
        return False
    boost = int(getattr(pair, "boost_score", 0) or 0)
    if boost >= 100:
        return False
    if pair.chg_h1 <= 0:
        return False
    age = pump.age_hours
    if age is None or age > 6:
        return False
    return pump.whale_signal
