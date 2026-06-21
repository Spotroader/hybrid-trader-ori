"""Funding + OI konfluans — Binance futures public API."""

from __future__ import annotations

import httpx

FAPI = "https://fapi.binance.com"


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def funding_oi_score(funding_pct: float, oi_change_pct: float) -> tuple[float, str]:
    """0..100 — aşırı kalabalık long cezalı; squeeze setup bonus."""
    fr = funding_pct * 100  # 0.0001 -> 0.01%
    score = 50.0
    note_parts = [f"funding {fr:.3f}%"]
    if fr > 0.05:
        score -= 25
        note_parts.append("long kalabalık")
    elif fr < -0.01 and oi_change_pct > 0:
        score += 20
        note_parts.append("squeeze potansiyeli")
    elif abs(fr) < 0.02 and oi_change_pct > 2:
        score += 15
        note_parts.append("sağlıklı OI artışı")
    if oi_change_pct > 5 and fr > 0.03:
        score -= 15
        note_parts.append("OI+funding ısınma")
    return round(_clip(score, 0, 100), 1), " · ".join(note_parts)


def scan_derivatives(symbols: list[str]) -> dict[str, dict]:
    """Sembol bazında türev skoru (Binance USDT-M varsa)."""
    out: dict[str, dict] = {}
    if not symbols:
        return out
    with httpx.Client() as client:
        try:
            prem = client.get(f"{FAPI}/fapi/v1/premiumIndex", timeout=12)
            prem.raise_for_status()
            funding_map = {
                p["symbol"]: float(p.get("lastFundingRate", 0))
                for p in prem.json()
                if p.get("symbol", "").endswith("USDT")
            }
        except Exception:
            return out

        for base in symbols:
            sym = f"{base}USDT"
            fr = funding_map.get(sym)
            if fr is None:
                continue
            oi_chg = 0.0
            try:
                oi_r = client.get(
                    f"{FAPI}/futures/data/openInterestHist",
                    params={"symbol": sym, "period": "1h", "limit": 2},
                    timeout=12,
                )
                if oi_r.status_code == 200:
                    rows = oi_r.json()
                    if len(rows) >= 2:
                        a, b = float(rows[-2]["sumOpenInterest"]), float(rows[-1]["sumOpenInterest"])
                        if a > 0:
                            oi_chg = (b - a) / a * 100
            except Exception:
                pass
            score, note = funding_oi_score(fr, oi_chg)
            out[base] = {
                "score": score,
                "funding_rate": round(fr * 100, 4),
                "oi_change_pct": round(oi_chg, 2),
                "reason": note,
            }
    return out
