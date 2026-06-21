"""OKX / Binance — tutulabilir yüksek potansiyel coin sıralaması."""

from __future__ import annotations

import httpx

from hibrit_trader.advanced_scan.cex_scan import (
    TOP_N,
    _binance_klines,
    _binance_universe,
    _okx_klines,
    _okx_universe,
    technical_score,
)


def _hold_score(score: float, metrics: dict) -> float:
    """Pump cezası düşük, trend + hacim dengeli — tutma potansiyeli."""
    chg = metrics.get("chg_24h_pct", 0)
    vol_sp = metrics.get("vol_spike", 1)
    rsi = metrics.get("rsi", 50)
    hold_bonus = 0.0
    if 5 <= chg <= 18:
        hold_bonus += 8
    if 1.2 <= vol_sp <= 2.5:
        hold_bonus += 6
    if 40 <= rsi <= 58:
        hold_bonus += 5
    if chg > 25:
        hold_bonus -= 12
    return round(min(100, score + hold_bonus), 1)


def _scan_exchange(
    client: httpx.Client,
    exchange: str,
    universe_fn,
    klines_fn,
    sym_key: str,
    limit: int,
) -> list[dict]:
    out: list[dict] = []
    for base, sym, vol24 in universe_fn(client, TOP_N):
        try:
            df = klines_fn(client, sym)
            if df is None:
                continue
            score, metrics = technical_score(df["close"], df["high"], df["low"], df["volume"])
            if score <= 0:
                continue
            hold = _hold_score(score, metrics)
            out.append(
                {
                    "symbol": base,
                    "exchange": exchange,
                    "score": hold,
                    "tech_score": score,
                    "vol_24h_usd": round(vol24),
                    "reason": (
                        f"Tutma {hold:.0f} · RSI {metrics.get('rsi')} · "
                        f"hacim x{metrics.get('vol_spike')} · 24s {metrics.get('chg_24h_pct')}%"
                    ),
                    "metrics": metrics,
                    "inst": sym,
                }
            )
        except Exception:
            continue
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def scan_binance_holds(limit: int = 12) -> list[dict]:
    with httpx.Client() as client:
        return _scan_exchange(
            client, "binance", _binance_universe, _binance_klines, "symbol", limit
        )


def scan_okx_holds(limit: int = 12) -> list[dict]:
    with httpx.Client() as client:
        return _scan_exchange(client, "okx", _okx_universe, _okx_klines, "instId", limit)
