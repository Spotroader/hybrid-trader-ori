"""Binance + OKX spot teknik tarama — public API, $0."""

from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd

from hibrit_trader.advanced_scan.indicators import (
    atr,
    chandelier_long_stop,
    ema,
    halftrend_bull,
    macd_hist,
    market_structure_bull,
    rsi,
    supertrend,
    ut_bot_alerts,
    volume_spike_ratio,
)

BINANCE = "https://api.binance.com"
OKX = "https://www.okx.com"
TOP_N = 25


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def technical_score(closes: pd.Series, highs: pd.Series, lows: pd.Series, volumes: pd.Series) -> tuple[float, dict]:
    """0..100 teknik skor + özet metrikler."""
    if len(closes) < 30:
        return 0.0, {}
    r = rsi(closes)
    hist = macd_hist(closes)
    ema200 = float(
        ema(closes, 200).iloc[-1]
        if len(closes) >= 200
        else ema(closes, min(50, len(closes) - 1)).iloc[-1]
    )
    price = float(closes.iloc[-1])
    vol_r = volume_spike_ratio(volumes)

    rsi_s = _clip((50 - abs(r - 45)) / 50, 0, 1) if 25 <= r <= 65 else (_clip(r / 35, 0, 0.5) if r < 35 else 0.2)
    macd_s = _clip(hist / max(price * 0.002, 1e-9), 0, 1)
    trend_s = 1.0 if price > ema200 else 0.3
    vol_s = _clip((vol_r - 1) / 2, 0, 1)
    chg = (price - float(closes.iloc[-24])) / float(closes.iloc[-24]) * 100 if len(closes) >= 24 else 0
    pump_pen = 0.0 if chg <= 15 else _clip((chg - 15) / 30, 0, 0.5)

    atr_val = atr(highs, lows, closes)
    st = supertrend(highs, lows, closes)
    ht = halftrend_bull(highs, lows, closes)
    msb = market_structure_bull(highs, lows, closes)
    ut = ut_bot_alerts(highs, lows, closes)
    ce_stop = chandelier_long_stop(highs, lows, closes)
    raw = 30 * rsi_s + 25 * macd_s + 25 * trend_s + 20 * vol_s
    score = round(_clip(raw - pump_pen * 100, 0, 100), 1)
    return score, {
        "rsi": round(r, 1),
        "macd_hist": round(hist, 6),
        "vol_spike": round(vol_r, 2),
        "chg_24h_pct": round(chg, 2),
        "above_ema200": bool(price > ema200),
        "atr_pct": round(atr_val / max(price, 1e-12) * 100, 2),
        "supertrend_bull": bool(st["in_uptrend"]),
        "supertrend_buy": bool(st["buy_signal"]),
        "supertrend_whipsaw": bool(st["whipsaw_risk"]),
        "halftrend_bull": bool(ht),
        "msb_bull": bool(msb),
        "ut_bot_bull": bool(ut["bull"]),
        "ut_bot_alert": bool(ut["buy_alert"]),
        "ut_bot_sell": bool(ut["sell_alert"]),
        "chandelier_stop": ce_stop,
        "chandelier_below": bool(price < ce_stop) if ce_stop > 0 else False,
    }


def _binance_klines(client: httpx.Client, symbol: str) -> Optional[pd.DataFrame]:
    r = client.get(
        f"{BINANCE}/api/v3/klines",
        params={"symbol": symbol, "interval": "1h", "limit": 120},
        timeout=12,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "tb", "tq", "ignore",
        ],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df


def _okx_klines(client: httpx.Client, inst_id: str) -> Optional[pd.DataFrame]:
    r = client.get(
        f"{OKX}/api/v5/market/candles",
        params={"instId": inst_id, "bar": "1H", "limit": 120},
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "0" or not data.get("data"):
        return None
    rows = list(reversed(data["data"]))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"])
    for col in ("open", "high", "low", "close", "vol"):
        df[col] = df[col].astype(float)
    df = df.rename(columns={"vol": "volume"})
    return df


def _binance_universe(client: httpx.Client, limit: int) -> list[tuple[str, str, float]]:
    r = client.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=15)
    r.raise_for_status()
    out: list[tuple[str, str, float]] = []
    for t in r.json():
        sym = t["symbol"]
        if not sym.endswith("USDT") or "UP" in sym or "DOWN" in sym or "BULL" in sym or "BEAR" in sym:
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol < 5_000_000:
            continue
        base = sym[:-4]
        out.append((base, sym, vol))
    out.sort(key=lambda x: -x[2])
    return out[:limit]


def _okx_universe(client: httpx.Client, limit: int) -> list[tuple[str, str, float]]:
    r = client.get(f"{OKX}/api/v5/market/tickers", params={"instType": "SPOT"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    out: list[tuple[str, str, float]] = []
    for t in data.get("data", []):
        inst = t.get("instId", "")
        if not inst.endswith("-USDT"):
            continue
        vol = float(t.get("volCcy24h", 0) or 0)
        if vol < 1_000_000:
            continue
        base = inst.split("-")[0]
        out.append((base, inst, vol))
    out.sort(key=lambda x: -x[2])
    return out[:limit]


def scan_cex(limit: int = 15) -> list[dict]:
    results: dict[str, dict] = {}
    with httpx.Client() as client:
        for base, sym, _ in _binance_universe(client, TOP_N):
            try:
                df = _binance_klines(client, sym)
                if df is None:
                    continue
                score, metrics = technical_score(df["close"], df["high"], df["low"], df["volume"])
                if score <= 0:
                    continue
                reason = f"RSI {metrics.get('rsi')} · hacim x{metrics.get('vol_spike')} · 24s {metrics.get('chg_24h_pct')}%"
                entry = {
                    "symbol": base,
                    "exchange": "binance",
                    "score": score,
                    "reason": reason,
                    "metrics": metrics,
                }
                prev = results.get(base)
                if not prev or score > prev["score"]:
                    results[base] = entry
            except Exception:
                continue

        for base, inst, _ in _okx_universe(client, TOP_N):
            try:
                df = _okx_klines(client, inst)
                if df is None:
                    continue
                score, metrics = technical_score(df["close"], df["high"], df["low"], df["volume"])
                if score <= 0:
                    continue
                reason = f"RSI {metrics.get('rsi')} · hacim x{metrics.get('vol_spike')} · 24s {metrics.get('chg_24h_pct')}%"
                entry = {
                    "symbol": base,
                    "exchange": "okx",
                    "score": score,
                    "reason": reason,
                    "metrics": metrics,
                }
                prev = results.get(base)
                if not prev or score > prev["score"]:
                    results[base] = entry
            except Exception:
                continue

    ranked = sorted(results.values(), key=lambda x: -x["score"])
    return ranked[:limit]
