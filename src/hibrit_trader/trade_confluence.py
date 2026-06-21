"""Birleşik trade konfluansı — DEX + CEX + balina + Saito + smart money tek skor.

Piyasa zekâsı panelde değil, giriş kapısında kullanılır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from hibrit_trader.cex_confluence import cex_hold_score, pair_base_symbol
from hibrit_trader.dex_trending_strategy import evaluate_trending, trending_fast_enabled
from hibrit_trader.pump_research import moonshot_entry_relax, moonshot_min_score
from hibrit_trader.scanner import Pair
from hibrit_trader.trend_stack import build_cex_metrics_index, trend_stack_for_symbol


def _aggressive_trading() -> bool:
    return os.getenv("PAPER_AGGRESSIVE", "1") != "0" or os.getenv("AGGRESSIVE_TRADING", "0") == "1"


@dataclass
class ConfluenceSnapshot:
    """Tek tick'te tüm harici kaynakların harmanlanmış görünümü."""

    cex_scores: dict[str, float]
    whale_by_symbol: dict[str, dict]
    brain_tam: set[str] = field(default_factory=set)
    brain_top: set[str] = field(default_factory=set)
    macro_avg: float | None = None
    brain_penalty: float = 0.0
    brain_regime: str | None = None
    cex_metrics: dict[str, dict] = field(default_factory=dict)
    confluence_min: float = 58.0
    min_layers: int = 2
    aggressive: bool = False


@dataclass
class ConfluenceResult:
    score: float
    layers: dict[str, bool]
    layer_count: int
    enter_ok: bool
    blocker: str | None
    breakdown: dict[str, float]
    layer_labels: list[str]

    def summary(self) -> str:
        tags = "+".join(self.layer_labels) if self.layer_labels else "—"
        return f"konfluans {self.score:.0f} ({tags})"


def build_whale_index(whale_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in whale_rows:
        sym = str(row.get("symbol", "")).upper()
        if sym:
            out[sym] = row
    return out


def build_confluence_snapshot(
    *,
    binance_holds: list[dict],
    okx_holds: list[dict],
    whale_signals: list[dict],
    brain_verdict,
    macro_avg: float | None,
    brain_penalty: float,
    confluence_min: float = 58.0,
    min_layers: int = 2,
    aggressive: bool | None = None,
) -> ConfluenceSnapshot:
    from hibrit_trader.cex_confluence import cex_symbol_scores

    cex = cex_symbol_scores(binance_holds, okx_holds)
    metrics = build_cex_metrics_index(binance_holds, okx_holds)
    tam: set[str] = set()
    top: set[str] = set()
    regime = None
    if brain_verdict is not None:
        regime = getattr(brain_verdict, "regime", None)
        for s in getattr(brain_verdict, "tam_isabet_symbols", []) or []:
            tam.add(str(s).upper())
        for row in getattr(brain_verdict, "top_picks", []) or []:
            sym = row.get("symbol") if isinstance(row, dict) else None
            if sym:
                top.add(str(sym).upper())

    return ConfluenceSnapshot(
        cex_scores=cex,
        whale_by_symbol=build_whale_index(whale_signals),
        brain_tam=tam,
        brain_top=top,
        macro_avg=macro_avg,
        brain_penalty=brain_penalty,
        brain_regime=regime,
        cex_metrics=metrics,
        confluence_min=confluence_min,
        min_layers=min_layers,
        aggressive=aggressive if aggressive is not None else _aggressive_trading(),
    )


def compute_trade_confluence(
    dex_score: float,
    pair: Pair,
    snap: ConfluenceSnapshot,
    *,
    entry_min: float,
    smart_money_ok: bool,
    smart_money_count: int = 0,
    moonshot_score: float = 0.0,
    founder_fast: bool = False,
    genesis_ok: bool = False,
) -> ConfluenceResult:
    sym = pair_base_symbol(pair)
    cex_hold = cex_hold_score(pair, snap.cex_scores)
    trend = trend_stack_for_symbol(sym, snap.cex_metrics, pair)
    ds_trend = evaluate_trending(pair)
    genesis_fast = genesis_ok and snap.aggressive
    ds_fast = (
        (trending_fast_enabled() and snap.aggressive and ds_trend.entry_ok)
        or founder_fast
        or genesis_fast
    )
    whale = snap.whale_by_symbol.get(sym)
    whale_score = float(whale.get("score", 0)) if whale else 0.0
    whale_buy = bool(whale.get("buy_signal")) if whale else False
    whale_wallets = int(whale.get("wallet_count", 0)) if whale else 0

    in_brain_tam = sym in snap.brain_tam
    in_brain_top = sym in snap.brain_top

    layers = {
        "dex": dex_score >= entry_min,
        "cex": cex_hold >= 45.0,
        "trend": trend.entry_ok or ds_fast,
        "whale": whale_buy or (whale_wallets >= 3 and whale_score >= 50),
        "smart": smart_money_ok,
        "brain": in_brain_tam or in_brain_top,
        "moon": moonshot_score >= moonshot_min_score(),
    }
    if ds_fast:
        layers["dex"] = True
    layer_count = sum(1 for v in layers.values() if v)
    layer_labels = [k.upper() for k, v in layers.items() if v]
    if ds_fast:
        layer_labels.append("DS")
    if founder_fast:
        layer_labels.append("FAST")
    if genesis_fast:
        layer_labels.append("GEN")
    if layers["moon"]:
        layer_labels.append("MOON")

    dex_pts = min(32.0, dex_score * 0.32)
    cex_pts = min(22.0, cex_hold * 0.22)
    trend_pts = min(25.0, trend.score * 0.25)
    if trend.entry_ok:
        trend_pts = min(25.0, trend_pts + 4.0)
    if ds_fast:
        trend_pts = min(28.0, max(trend_pts, ds_trend.score * 0.28))
    whale_pts = min(18.0, whale_score * 0.18)
    if whale_buy:
        whale_pts = min(18.0, whale_pts + 4.0)
    smart_pts = 8.0 if smart_money_ok else (3.0 if snap.aggressive else 0.0)
    brain_pts = 0.0
    if in_brain_tam:
        brain_pts = 8.0
    elif in_brain_top:
        brain_pts = 5.0
    penalty_scale = 0.15 if snap.aggressive else 0.25
    brain_pts = max(0.0, brain_pts - snap.brain_penalty * penalty_scale)

    macro_pts = 0.0
    if snap.macro_avg is not None:
        if snap.macro_avg >= 50:
            macro_pts = 5.0
        elif snap.macro_avg < 38:
            macro_pts = -8.0

    moon_pts = 0.0
    if moonshot_score >= moonshot_min_score():
        moon_pts = min(14.0, (moonshot_score - 50) * 0.22)

    total = round(
        max(0.0, min(100.0, dex_pts + cex_pts + trend_pts + whale_pts + smart_pts + brain_pts + macro_pts + moon_pts)),
        1,
    )
    breakdown = {
        "dex": round(dex_pts, 1),
        "cex": round(cex_pts, 1),
        "trend": round(trend_pts, 1),
        "whale": round(whale_pts, 1),
        "smart": round(smart_pts, 1),
        "brain": round(brain_pts, 1),
        "macro": round(macro_pts, 1),
        "moon": round(moon_pts, 1),
        "ds_trend": round(ds_trend.score, 1) if ds_fast else 0.0,
    }

    eff_conf_min = snap.confluence_min
    if layers["moon"] and snap.aggressive:
        eff_conf_min = max(38.0, eff_conf_min - moonshot_entry_relax())
    if founder_fast and snap.aggressive:
        eff_conf_min = max(
            35.0,
            eff_conf_min - float(os.getenv("FOUNDER_FAST_CONF_RELAX", "8")),
        )
    if genesis_fast:
        eff_conf_min = max(
            32.0,
            eff_conf_min - float(os.getenv("GENESIS_CONF_RELAX", "14")),
        )

    blocker = None
    enter_ok = True
    eff_min_layers = 1 if (ds_fast and snap.aggressive) else snap.min_layers
    if founder_fast and snap.aggressive:
        eff_min_layers = 1
    if genesis_fast:
        eff_min_layers = 1
    if layers["moon"] and snap.aggressive and eff_min_layers > 1:
        eff_min_layers = 1
    if layer_count < eff_min_layers:
        enter_ok = False
        blocker = f"katman yetersiz ({layer_count}<{eff_min_layers}: {','.join(layer_labels) or 'yok'})"
    elif total < eff_conf_min:
        enter_ok = False
        blocker = f"konfluans {total:.0f}<{eff_conf_min:.0f}"
    elif not trend.entry_ok and not ds_fast:
        enter_ok = False
        blocker = f"Supertrend: {trend.reason}"
    elif snap.brain_regime == "risk_off" and layer_count < 3 and not snap.aggressive:
        enter_ok = False
        blocker = "Saito risk_off — 3+ katman gerekli"

    return ConfluenceResult(
        score=total,
        layers=layers,
        layer_count=layer_count,
        enter_ok=enter_ok,
        blocker=blocker,
        breakdown=breakdown,
        layer_labels=layer_labels,
    )
