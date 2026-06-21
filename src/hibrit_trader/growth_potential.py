"""Artış potansiyeli — DEX momentum + CEX tut + balina + Saito tek durum skoru.

Kaynaklar (mevcut motor, yeni API yok):
- score.py / decision.expected_move_pct — momentum & kenar
- hold_ranking — CEX tut skoru
- trade_confluence — katman uyumu
- advanced_scan tam_isabet — Saito/brain sembolleri
"""

from __future__ import annotations

from hibrit_trader.cex_confluence import cex_hold_score, pair_base_symbol
from hibrit_trader.decision import MAX_CHASE_H1_PCT, expected_move_pct
from hibrit_trader.early_launch import genesis_score, is_trending_late_pump
from hibrit_trader.scanner import Pair
from hibrit_trader.trade_confluence import build_whale_index

STAGE_LABELS = {
    "erken": "Erken ivme",
    "ivme": "Güçlü ivme",
    "trend": "Trend",
    "cex_erken": "CEX önde",
    "gec_pump": "Geç pump",
    "zayif": "Zayıf",
}

STAGE_PRIORITY = {
    "erken": 5,
    "ivme": 4,
    "cex_erken": 3,
    "trend": 2,
    "gec_pump": 0,
    "zayif": 0,
}


def _vol_spike(pair: Pair) -> float:
    return (pair.vol_m5 * 12) / max(pair.vol_h1, 1.0)


def classify_growth_stage(pair: Pair, *, cex_hold: float = 0.0) -> str:
    h1 = pair.chg_h1
    m5 = pair.chg_m5
    vol = _vol_spike(pair)

    if is_trending_late_pump(pair):
        return "gec_pump"
    if genesis_score(pair) >= 52:
        return "erken"
    if h1 >= MAX_CHASE_H1_PCT:
        return "gec_pump"
    if h1 <= 0 and m5 <= 0:
        if cex_hold >= 55:
            return "cex_erken"
        return "zayif"
    if 2 <= h1 <= 14 and m5 > 0.5 and vol >= 1.25:
        return "erken"
    if 8 <= h1 <= 28 and vol >= 1.4:
        return "ivme"
    if h1 > 0 or m5 > 0:
        return "trend"
    return "zayif"


def compute_growth_potential(
    dex_score: float,
    pair: Pair,
    *,
    cex_hold: float = 0.0,
    whale_row: dict | None = None,
    in_brain_tam: bool = False,
    in_brain_top: bool = False,
    confluence_score: float | None = None,
) -> dict:
    stage = classify_growth_stage(pair, cex_hold=cex_hold)
    move = expected_move_pct(pair, cex_hold_score=cex_hold)
    vol = _vol_spike(pair)

    upside = (
        move * 2.8
        + dex_score * 0.35
        + (cex_hold * 0.22 if cex_hold >= 45 else cex_hold * 0.08)
    )
    if whale_row and whale_row.get("buy_signal"):
        upside += 8
    elif whale_row and int(whale_row.get("wallet_count", 0)) >= 3:
        upside += 5
    if in_brain_tam:
        upside += 10
    elif in_brain_top:
        upside += 5
    if confluence_score is not None and confluence_score >= 65:
        upside += 6

    if stage == "gec_pump":
        upside *= 0.35
    elif stage == "zayif":
        upside *= 0.5
    elif stage == "erken":
        upside += 8
    elif stage == "ivme":
        upside += 4

    upside = round(max(0.0, min(100.0, upside)), 1)

    signals: list[str] = []
    if vol >= 1.4:
        signals.append(f"hacim x{vol:.1f}")
    if pair.chg_m5 > 0:
        signals.append(f"m5 +{pair.chg_m5:.1f}%")
    if cex_hold >= 55:
        signals.append(f"CEX tut {cex_hold:.0f}")
    if whale_row and whale_row.get("buy_signal"):
        signals.append("balina AL")
    if in_brain_tam:
        signals.append("Saito tam")
    elif in_brain_top:
        signals.append("Saito top")

    action_hint = "izle"
    if stage in ("erken", "ivme") and upside >= 55:
        action_hint = "aday"
    elif stage == "gec_pump":
        action_hint = "kaçın"
    elif stage == "cex_erken":
        action_hint = "dex_bekle"

    return {
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "upside_score": upside,
        "expected_move_pct": round(move, 1),
        "dex_score": round(dex_score, 1),
        "cex_hold": round(cex_hold, 1) if cex_hold else None,
        "signals": signals,
        "action_hint": action_hint,
        "h1_pct": round(pair.chg_h1, 1),
        "vol_spike": round(vol, 2),
    }


def build_growth_watchlist(
    ranked: list[tuple[float, Pair]],
    *,
    cex_scores: dict[str, float],
    whale_signals: list[dict],
    brain_tam: set[str] | None = None,
    brain_top: set[str] | None = None,
    confluence_by_pool: dict[str, float] | None = None,
    binance_holds: list[dict] | None = None,
    okx_holds: list[dict] | None = None,
    limit: int = 12,
) -> list[dict]:
    """DEX izleme + CEX-erken semboller — artış potansiyeline göre sıralı."""
    whale_idx = build_whale_index(whale_signals or [])
    tam = brain_tam or set()
    top = brain_top or set()
    conf_map = confluence_by_pool or {}
    dex_symbols: set[str] = set()
    rows: list[dict] = []

    for dex_score, pair in ranked[:25]:
        sym = pair_base_symbol(pair)
        dex_symbols.add(sym)
        cex_hold = cex_hold_score(pair, cex_scores)
        growth = compute_growth_potential(
            dex_score,
            pair,
            cex_hold=cex_hold,
            whale_row=whale_idx.get(sym),
            in_brain_tam=sym in tam,
            in_brain_top=sym in top,
            confluence_score=conf_map.get(pair.pool_address),
        )
        if growth["stage"] in ("zayif", "gec_pump") and growth["upside_score"] < 40:
            continue
        rows.append(
            {
                "symbol": sym,
                "name": pair.name,
                "chain": pair.chain,
                "source": "dex",
                **growth,
            }
        )

    for hold_row in (binance_holds or []) + (okx_holds or []):
        sym = str(hold_row.get("symbol", "")).upper()
        if not sym or sym in dex_symbols:
            continue
        hold = float(hold_row.get("score", 0))
        if hold < 52:
            continue
        rows.append(
            {
                "symbol": sym,
                "name": f"{sym}/USDT",
                "chain": "cex",
                "source": "cex",
                "stage": "cex_erken",
                "stage_label": STAGE_LABELS["cex_erken"],
                "upside_score": round(min(100, hold * 0.85 + 8), 1),
                "expected_move_pct": round(min(hold / 8, 18), 1),
                "dex_score": None,
                "cex_hold": round(hold, 1),
                "signals": [hold_row.get("reason", "CEX tut")[:80]],
                "action_hint": "dex_bekle",
                "h1_pct": None,
                "vol_spike": None,
            }
        )

    rows.sort(
        key=lambda r: (
            -STAGE_PRIORITY.get(r["stage"], 0),
            -r["upside_score"],
        )
    )
    return rows[:limit]
