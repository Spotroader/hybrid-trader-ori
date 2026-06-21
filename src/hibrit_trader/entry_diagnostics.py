"""Giriş kapıları teşhisi — watchlist adayları için skip nedeni (Faz 8)."""

from __future__ import annotations

import os

from hibrit_trader.cex_confluence import cex_boost_points, cex_hold_score, cex_symbol_scores
from hibrit_trader.decision import DecisionPolicy, evaluate_entry, has_profit_edge
from hibrit_trader.dex_trending_strategy import evaluate_trending
from hibrit_trader.early_launch import classify_pump_window, genesis_entry_ok, pump_entry_ok
from hibrit_trader.position_sizer import compute_position_usd
from hibrit_trader.safety import SafetyReport, entry_safety_ok
from hibrit_trader.scanner import Pair
from hibrit_trader.score import opportunity_score
from hibrit_trader.smart_money import smart_money_entry_ok, wallet_buyer_info
from hibrit_trader.token_filters import token_filter_ok
from hibrit_trader.trade_confluence import (
    ConfluenceSnapshot,
    build_confluence_snapshot,
    compute_trade_confluence,
)


def _safety_from_cache(
    safety_cache: dict[str, tuple[float, SafetyReport]],
    chain: str,
    token: str,
) -> SafetyReport | None:
    key = f"{chain}:{token}"
    cached = safety_cache.get(key)
    return cached[1] if cached else None


def diagnose_pair(
    score: float,
    pair: Pair,
    *,
    policy: DecisionPolicy,
    position_usd: float,
    macro_avg: float | None,
    brain_penalty: float,
    cex_scores: dict[str, float],
    safety: SafetyReport | None,
    smart_money_ok: bool,
    smart_money_note: str,
    kill_switch: bool,
    open_count: int,
    max_open: int,
    daily_pnl: float,
    daily_loss_limit: float,
    already_held: bool,
    live_allowed: bool,
    quote_slippage_pct: float = 0.0,
    confluence_snap: ConfluenceSnapshot | None = None,
    smart_money_count: int = 0,
    confluence_required: bool = True,
) -> dict:
    base = opportunity_score(pair, position_usd)
    boost, cex_sym = cex_boost_points(pair, cex_scores)
    hold = cex_hold_score(pair, cex_scores)
    entry_min = policy.effective_entry_min(macro_avg, brain_penalty)
    pump_window = classify_pump_window(pair)
    genesis_ok, gen_note = pump_entry_ok(pair)
    if genesis_ok:
        entry_min = min(entry_min, float(os.getenv("GENESIS_ENTRY_MIN", "52")))
    filter_ok, filter_note = token_filter_ok(pair, genesis_ok=genesis_ok)
    edge_ok, edge_note = has_profit_edge(
        pair,
        position_usd,
        policy,
        quote_slippage_pct=quote_slippage_pct,
        cex_hold_score=hold,
        trending_ok=False,
        genesis_ok=genesis_ok,
    )
    ds_sig = evaluate_trending(pair)
    trending_ok = ds_sig.entry_ok or genesis_ok

    gates = {
        "score": {
            "ok": score >= entry_min,
            "value": score,
            "need": entry_min,
            "base_score": base,
            "cex_boost": boost,
        },
        "momentum": {
            "ok": pair.chg_h1 > 0 or pair.chg_m5 > 0 or hold >= 45,
            "h1": round(pair.chg_h1, 2),
            "m5": round(pair.chg_m5, 2),
            "cex_hold": round(hold, 1),
        },
        "filter": {"ok": filter_ok, "detail": filter_note},
        "edge": {"ok": edge_ok, "detail": edge_note},
        "smart_money": {
            "ok": (not policy.require_smart_money) or smart_money_ok,
            "detail": smart_money_note,
            "required": policy.require_smart_money,
        },
        "safety": {
            "ok": safety.ok if safety else None,
            "detail": "; ".join(safety.reasons[:2])
            if safety and not safety.ok
            else ("henüz kontrol edilmedi" if safety is None else "OK"),
        },
        "pump_window": pump_window,
        "genesis": {"ok": genesis_ok, "detail": gen_note},
    }

    decision = evaluate_entry(
        score,
        pair,
        position_usd,
        policy,
        safety_ok=entry_safety_ok(safety, genesis_ok=genesis_ok)[0] if safety else False,
        kill_switch=kill_switch,
        open_count=open_count,
        daily_pnl=daily_pnl,
        daily_loss_limit=daily_loss_limit,
        already_held=already_held,
        live_allowed=live_allowed,
        macro_avg=macro_avg,
        brain_penalty=brain_penalty,
        quote_slippage_pct=quote_slippage_pct,
        smart_money_ok=smart_money_ok,
        smart_money_note=smart_money_note,
        cex_hold_score=hold,
        trending_ok=trending_ok,
        genesis_ok=genesis_ok,
    )

    conf_out = None
    conf = None
    if confluence_snap is not None:
        conf = compute_trade_confluence(
            score,
            pair,
            confluence_snap,
            entry_min=entry_min,
            smart_money_ok=smart_money_ok,
            smart_money_count=smart_money_count,
            genesis_ok=genesis_ok,
        )
        conf_out = {
            "score": conf.score,
            "layers": conf.layer_labels,
            "layer_count": conf.layer_count,
            "enter_ok": conf.enter_ok,
            "blocker": conf.blocker,
            "breakdown": conf.breakdown,
        }

    if safety is None:
        would_enter = False
        blocker = "güvenlik bekleniyor"
    elif confluence_required and conf is not None and not conf.enter_ok:
        would_enter = False
        blocker = conf.blocker
    elif decision.action != "enter":
        blocker = decision.reason
        would_enter = False
    else:
        blocker = None
        would_enter = True

    return {
        "pair": pair.name,
        "chain": pair.chain,
        "score": score,
        "cex_symbol": cex_sym,
        "cex_hold_score": round(hold, 1) if hold else None,
        "would_enter": would_enter,
        "blocker": blocker,
        "gates": gates,
        "confluence": conf_out,
        "pump_window": pump_window["window"],
        "pump_label": pump_window["label"],
    }


def build_entry_diagnostics(
    ranked: list[tuple[float, Pair]],
    *,
    policy: DecisionPolicy,
    settings,
    broker,
    macro_avg: float | None,
    brain_penalty: float,
    binance_holds: list[dict],
    okx_holds: list[dict],
    safety_cache: dict[str, tuple[float, SafetyReport]],
    kill_switch: bool,
    held_tokens: set[str],
    live_allowed: bool,
    daily_pnl: float = 0.0,
    limit: int = 12,
    client=None,
    whale_signals: list[dict] | None = None,
    brain_verdict=None,
    confluence_required: bool = True,
) -> list[dict]:
    cex_scores = cex_symbol_scores(binance_holds, okx_holds)
    conf_snap = build_confluence_snapshot(
        binance_holds=binance_holds,
        okx_holds=okx_holds,
        whale_signals=whale_signals or [],
        brain_verdict=brain_verdict,
        macro_avg=macro_avg,
        brain_penalty=brain_penalty,
        confluence_min=getattr(settings, "confluence_min", 58.0),
        min_layers=getattr(settings, "confluence_min_layers", 2),
    )
    held = set(held_tokens)
    rows: list[dict] = []
    for skor, pair in ranked[:limit]:
        position_usd = compute_position_usd(settings, broker, pair)
        genesis_ok, _ = pump_entry_ok(pair)
        sm_count, sm_src = wallet_buyer_info(pair, client=client)
        if genesis_ok:
            sm_ok, sm_note = True, f"genesis · {sm_count} ({sm_src})"
        elif not policy.require_smart_money:
            sm_ok, sm_note = True, f"proxy {sm_count} ({sm_src})"
        else:
            sm_ok, sm_note = smart_money_entry_ok(pair, policy.min_alpha_wallets, client=client)
        safety = _safety_from_cache(safety_cache, pair.chain, pair.token_address)
        rows.append(
            diagnose_pair(
                skor,
                pair,
                policy=policy,
                position_usd=position_usd,
                macro_avg=macro_avg,
                brain_penalty=brain_penalty,
                cex_scores=cex_scores,
                safety=safety,
                smart_money_ok=sm_ok,
                smart_money_note=sm_note,
                kill_switch=kill_switch,
                open_count=len(broker.positions),
                max_open=policy.max_open_positions,
                daily_pnl=daily_pnl,
                daily_loss_limit=settings.daily_loss_limit_usd,
                already_held=pair.token_address in held,
                live_allowed=live_allowed,
                confluence_snap=conf_snap,
                smart_money_count=sm_count,
                confluence_required=confluence_required,
            )
        )
    rows.sort(key=lambda r: (-(r.get("confluence") or {}).get("score", 0), -r["score"]))
    return rows
