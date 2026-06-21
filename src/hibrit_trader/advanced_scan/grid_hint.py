"""Dinamik grid ipucu — yürütme yok, ATR aralık önerisi."""

from __future__ import annotations

import httpx
import pandas as pd

from hibrit_trader.advanced_scan.indicators import atr, rsi


def grid_hints(symbols: list[str], limit: int = 10) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with httpx.Client() as client:
        for base in symbols[:limit]:
            sym = f"{base}USDT"
            try:
                r = client.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": sym, "interval": "4h", "limit": 60},
                    timeout=12,
                )
                r.raise_for_status()
                rows = r.json()
                df = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", "v"] + list(range(6)))
                for col in ("h", "l", "c"):
                    df[col] = df[col].astype(float)
                price = float(df["c"].iloc[-1])
                a = atr(df["h"], df["l"], df["c"])
                r_val = rsi(df["c"])
                low = round(price - 2 * a, 6)
                high = round(price + 2 * a, 6)
                mode = "DCA kademeli" if r_val < 40 else ("geniş grid" if r_val > 60 else "dar grid")
                out[base] = {
                    "score": 60.0,
                    "grid_low": low,
                    "grid_high": high,
                    "reason": f"ATR grid {low}-{high} · RSI {r_val:.0f} · {mode} (Faz 6 — işlem yok)",
                }
            except Exception:
                continue
    return out
