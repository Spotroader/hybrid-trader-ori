"""Birleşik trend katmanı — Supertrend + UT Bot + EMA200 + DEX fallback.

Giriş: ST AL + onay (HT/hacim/UT alert). CEX yoksa DEX momentum köprüsü.
Çıkış: Chandelier Exit → exit_policy runner trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hibrit_trader.scanner import Pair

PRIMARY_INDICATOR = "supertrend"


@dataclass
class TrendStackResult:
    score: float
    supertrend: bool
    halftrend: bool
    ut_bot: bool
    ema_filter: bool
    volume_ok: bool
    structure_ok: bool
    entry_ok: bool
    whipsaw_risk: bool
    primary: str = PRIMARY_INDICATOR
    signal_count: int = 0
    labels: list[str] = field(default_factory=list)
    reason: str = ""
    dex_fallback: bool = False
    chandelier_stop: float = 0.0


def build_cex_metrics_index(
    binance_holds: list[dict],
    okx_holds: list[dict],
) -> dict[str, dict]:
    """Sembol → en zengin CEX metrik seti (Binance + OKX birleşik)."""
    out: dict[str, dict] = {}
    for row in binance_holds + okx_holds:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        metrics = row.get("metrics") or {}
        if not metrics:
            continue
        prev = out.get(sym)
        if prev is None or len(metrics) > len(prev):
            out[sym] = dict(metrics)
    return out


def dex_trend_metrics(pair: Pair) -> dict:
    """CEX eşleşmesi yoksa DEX fiyat/hacimden trend proxy."""
    vol_h1 = float(pair.vol_h1 or 0)
    vol_m5 = float(pair.vol_m5 or 0)
    chg_h1 = float(pair.chg_h1 or 0)
    chg_m5 = float(pair.chg_m5 or 0)
    chg_h24 = float(pair.chg_h24 or 0)
    vol_spike = 1.0
    if vol_h1 > 0:
        vol_spike = max(1.0, vol_m5 / max(vol_h1 / 12.0, 1e-9))
    st = chg_h1 >= 1.2 and chg_m5 > 0
    ut = chg_m5 >= 0.8 and chg_h1 >= 2.0 and vol_spike >= 1.15
    return {
        "dex_source": True,
        "above_ema200": chg_h24 > -10.0,
        "vol_spike": round(vol_spike, 2),
        "supertrend_bull": st,
        "supertrend_buy": chg_m5 >= 1.0 and st,
        "supertrend_whipsaw": abs(chg_h1) < 0.4 and abs(chg_m5) < 0.25,
        "halftrend_bull": chg_h1 >= 2.5 and chg_m5 > 0,
        "msb_bull": chg_m5 >= 1.5 and chg_h1 >= max(chg_h24 * 0.2, 1.0),
        "ut_bot_bull": ut,
        "ut_bot_alert": ut and chg_m5 >= 1.2,
        "chg_24h_pct": chg_h24,
        "macd_hist": 0.001 if chg_m5 > 0 else 0.0,
    }


def _ut_bot_momentum(m: dict) -> bool:
    """Legacy UT proxy — CEX'te ut_bot_* yoksa."""
    if m.get("ut_bot_alert") or m.get("ut_bot_bull"):
        return True
    vol = float(m.get("vol_spike", 1))
    chg = float(m.get("chg_24h_pct", 0))
    macd = float(m.get("macd_hist", 0))
    return vol >= 1.35 and macd > 0 and chg >= 2.5


def compute_trend_stack(metrics: dict | None) -> TrendStackResult:
    if not metrics:
        return TrendStackResult(
            0.0,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            PRIMARY_INDICATOR,
            0,
            [],
            "CEX metrik yok",
        )

    dex_src = bool(metrics.get("dex_source", False))
    ema_ok = bool(metrics.get("above_ema200", False))
    vol_ok = float(metrics.get("vol_spike", 1)) >= 1.12
    st = bool(metrics.get("supertrend_bull", False))
    st_buy = bool(metrics.get("supertrend_buy", False))
    whipsaw = bool(metrics.get("supertrend_whipsaw", False))
    ht = bool(metrics.get("halftrend_bull", False))
    msb = bool(metrics.get("msb_bull", False))
    ut_alert = bool(metrics.get("ut_bot_alert", False))
    ut_bull = bool(metrics.get("ut_bot_bull", False)) or ut_alert or _ut_bot_momentum(metrics)
    ce_stop = float(metrics.get("chandelier_stop", 0) or 0)

    labels: list[str] = []
    if st:
        labels.append("ST")
    if ht:
        labels.append("HT")
    if ut_bull or ut_alert:
        labels.append("UT")
    if msb:
        labels.append("MSB")
    if dex_src:
        labels.append("DEX")

    confirm = ht or vol_ok or st_buy or ut_alert
    structure_ok = msb or st_buy or (vol_ok and ht) or (ut_alert and vol_ok)

    classic = ema_ok and st and confirm and structure_ok and not whipsaw
    ut_path = ema_ok and st and (ut_alert or (ut_bull and vol_ok)) and (msb or st_buy or ht) and not whipsaw
    dex_path = dex_src and ema_ok and st and (ut_alert or ht or vol_ok) and not whipsaw
    entry_ok = classic or ut_path or dex_path

    pts = 0.0
    if ema_ok:
        pts += 15
    if vol_ok:
        pts += 10
    if st:
        pts += 28
    if ht:
        pts += 16
    if msb:
        pts += 12
    if st_buy:
        pts += 8
    if ut_bull or ut_alert:
        pts += 10 if ut_alert else 6
    if entry_ok:
        pts += 10
    if whipsaw:
        pts -= 15

    score = round(max(0.0, min(100.0, pts)), 1)

    if not ema_ok:
        reason = "200 EMA altı — trend kapalı"
    elif whipsaw:
        reason = "Yatay/testere — whipsaw, bekle"
    elif not st:
        reason = "Supertrend SAT — AL bekle"
    elif entry_ok and ut_alert:
        reason = f"UT Bot + ST ({'+'.join(labels)})"
    elif entry_ok and dex_src:
        reason = f"DEX köprü ST ({'+'.join(labels)})"
    elif entry_ok:
        reason = f"Supertrend AL ({'+'.join(labels)})"
    elif not confirm:
        reason = "ST AL — HT/hacim/UT onayı yok"
    else:
        reason = "Yapı/hacim kırılımı zayıf"

    return TrendStackResult(
        score=score,
        supertrend=st,
        halftrend=ht,
        ut_bot=ut_bull or ut_alert,
        ema_filter=ema_ok,
        volume_ok=vol_ok,
        structure_ok=structure_ok,
        entry_ok=entry_ok,
        whipsaw_risk=whipsaw,
        primary=PRIMARY_INDICATOR,
        signal_count=sum(1 for x in (st, ht, ut_bull or ut_alert, msb) if x),
        labels=labels,
        reason=reason,
        dex_fallback=dex_src,
        chandelier_stop=ce_stop,
    )


def trend_stack_for_symbol(
    sym: str,
    metrics_index: dict[str, dict],
    pair: Pair | None = None,
) -> TrendStackResult:
    m = metrics_index.get(sym.upper())
    if not m and pair is not None:
        m = dex_trend_metrics(pair)
    return compute_trend_stack(m)
