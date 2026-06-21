"""Teknik indikatörler — saf pandas, test edilebilir."""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    if delta.abs().sum() == 0:
        return 50.0
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-12)
    val = 100 - (100 / (1 + rs))
    return float(val.iloc[-1])


def macd_hist(closes: pd.Series) -> float:
    if len(closes) < 35:
        return 0.0
    line = ema(closes, 12) - ema(closes, 26)
    signal = ema(line, 9)
    return float((line - signal).iloc[-1])


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return 0.0
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def volume_spike_ratio(volumes: pd.Series, lookback: int = 20) -> float:
    if len(volumes) < lookback + 1:
        return 1.0
    avg = volumes.iloc[-lookback - 1 : -1].mean()
    if avg <= 0:
        return 1.0
    return float(volumes.iloc[-1] / avg)


def _true_range_series(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> dict:
    """Supertrend yönü — bull=1, bear=-1. TradingView uyumlu basit uygulama."""
    n = len(close)
    empty = {
        "direction": 0,
        "in_uptrend": False,
        "buy_signal": False,
        "sell_signal": False,
        "line": 0.0,
        "whipsaw_risk": False,
    }
    if n < period + 2:
        return empty

    hl2 = (high + low) / 2.0
    tr = _true_range_series(high, low, close)
    atr_s = tr.rolling(period).mean()

    upper = hl2 + multiplier * atr_s
    lower = hl2 - multiplier * atr_s

    final_upper = upper.copy()
    final_lower = lower.copy()
    for i in range(1, n):
        if pd.notna(final_upper.iloc[i - 1]):
            final_upper.iloc[i] = min(upper.iloc[i], final_upper.iloc[i - 1]) if close.iloc[i - 1] <= final_upper.iloc[i - 1] else upper.iloc[i]
        if pd.notna(final_lower.iloc[i - 1]):
            final_lower.iloc[i] = max(lower.iloc[i], final_lower.iloc[i - 1]) if close.iloc[i - 1] >= final_lower.iloc[i - 1] else lower.iloc[i]

    direction = pd.Series(1, index=close.index, dtype=int)
    for i in range(1, n):
        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

    cur = int(direction.iloc[-1])
    prev = int(direction.iloc[-2])
    line = float(final_lower.iloc[-1] if cur == 1 else final_upper.iloc[-1])
    flips = int((direction.diff().abs() > 0).iloc[-8:].sum()) if n >= 8 else 0

    return {
        "direction": cur,
        "in_uptrend": bool(cur == 1),
        "buy_signal": bool(cur == 1 and prev == -1),
        "sell_signal": bool(cur == -1 and prev == 1),
        "line": round(line, 8),
        "whipsaw_risk": bool(flips >= 2),
    }


def halftrend_bull(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    amplitude: int = 2,
) -> bool:
    """HalfTrend proxy — gürültü azaltılmış yön (ATR kanalı, yalnız trend yönünde kayar)."""
    n = len(close)
    if n < 20:
        return False
    atr_v = _true_range_series(high, low, close).rolling(14).mean().iloc[-1]
    if pd.isna(atr_v) or atr_v <= 0:
        return False
    mid = (high + low) / 2.0
    trail = float(mid.iloc[-1])
    trend_up = True
    for i in range(n - 20, n):
        m = float(mid.iloc[i])
        if trend_up:
            trail = max(trail, m - amplitude * float(atr_v))
            if float(close.iloc[i]) < trail:
                trend_up = False
                trail = m + amplitude * float(atr_v)
        else:
            trail = min(trail, m + amplitude * float(atr_v))
            if float(close.iloc[i]) > trail:
                trend_up = True
                trail = m - amplitude * float(atr_v)
    return trend_up


def market_structure_bull(high: pd.Series, low: pd.Series, close: pd.Series) -> bool:
    """MSB/CHoCH proxy — swing high kırılımı + higher low."""
    if len(close) < 12:
        return False
    prev_high = float(high.iloc[-12:-6].max())
    prev_low = float(low.iloc[-12:-6].min())
    recent_low = float(low.iloc[-6:].min())
    price = float(close.iloc[-1])
    return price > prev_high and recent_low > prev_low


def ut_bot_alerts(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    key_value: float = 1.0,
    atr_period: int = 10,
) -> dict:
    """UT Bot Alerts proxy — ATR trailing stop kırılımı."""
    n = len(close)
    empty = {"bull": False, "buy_alert": False, "sell_alert": False}
    if n < atr_period + 3:
        return empty

    tr = _true_range_series(high, low, close)
    atr_s = tr.rolling(atr_period).mean()
    offset = key_value * atr_s
    trail = close - offset

    bull = True
    for i in range(n - atr_period, n):
        if pd.isna(trail.iloc[i]):
            continue
        if float(close.iloc[i]) < float(trail.iloc[i]):
            bull = False
        elif float(close.iloc[i]) > float(trail.iloc[i]):
            bull = True

    buy = bool(
        bull
        and float(close.iloc[-1]) > float(trail.iloc[-1])
        and float(close.iloc[-2]) <= float(trail.iloc[-2])
    )
    sell = bool(
        (not bull)
        and float(close.iloc[-1]) < float(trail.iloc[-1])
        and float(close.iloc[-2]) >= float(trail.iloc[-2])
    )

    return {"bull": bool(bull), "buy_alert": buy, "sell_alert": sell}


def chandelier_long_stop(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 22,
    multiplier: float = 3.0,
) -> float:
    """Chandelier Exit long stop = highest high(period) - ATR(period)*mult."""
    if len(close) < period + 1:
        return 0.0
    tr = _true_range_series(high, low, close)
    hh = float(high.iloc[-period:].max())
    atr_v = float(tr.rolling(period).mean().iloc[-1])
    if atr_v <= 0:
        return 0.0
    return round(hh - multiplier * atr_v, 8)
