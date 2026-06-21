"""Kârlılık odaklı alım/satım kararı — tek kaynak.

DEX bot (on-chain) her tick:
  1) Güvenlik (GoPlus) geçmeden alım yok
  2) Skor + maliyet sonrası beklenen kenar (edge) yeterli olmalı
  3) Çıkış: katmanlı ladder (scratch, ATR stop, kademeli TP, trail, theta)
  4) Günlük zarar limiti / kill-switch / max pozisyon

Saito: yalnız giriş cezası + rejime göre ExitPolicy ayarı.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from hibrit_trader.config import GAS_COST_USD
from hibrit_trader.exit_policy import ExitDecision, ExitPolicy, evaluate_exit_ladder
from hibrit_trader.peak_intelligence import ExitContext
from hibrit_trader.paper import Position
from hibrit_trader.scanner import Pair
from hibrit_trader.token_filters import token_filter_ok

Action = Literal["enter", "hold", "exit", "skip", "exit_partial"]

# Trend listesinde geç kalınmış pump — giriş yasak (Faz 9)
MAX_CHASE_H1_PCT = 45.0


@dataclass
class DecisionPolicy:
    """Tüm eşikler tek yerde — kârlılık önceliği sabit."""

    entry_score_min: float = 55.0
    exit_score_max: float = 45.0
    take_profit_pct: float = 20.0
    stop_loss_pct: float = -8.0
    max_open_positions: int = 3
    missing_ticks_exit: int = 3
    min_edge_after_cost_pct: float = 4.0
    macro_risk_off_score: float = 38.0
    macro_entry_penalty: float = 10.0
    require_smart_money: bool = True
    min_alpha_wallets: int = 3

    def effective_entry_min(self, macro_avg: float | None, brain_penalty: float = 0.0) -> float:
        base = self.entry_score_min
        if macro_avg is not None and macro_avg < self.macro_risk_off_score:
            base = self.entry_score_min + self.macro_entry_penalty
        return base + max(brain_penalty, 0.0)

    def base_exit_policy(self) -> ExitPolicy:
        return ExitPolicy(
            stop_loss_pct=self.stop_loss_pct,
            exit_score_max=self.exit_score_max,
            missing_ticks_exit=self.missing_ticks_exit,
        )

    def summary(self) -> dict:
        ep = self.base_exit_policy().summary()
        return {
            "entry_score_min": self.entry_score_min,
            "exit_score_max": self.exit_score_max,
            "stop_loss_pct": self.stop_loss_pct,
            "max_open_positions": self.max_open_positions,
            "min_edge_after_cost_pct": self.min_edge_after_cost_pct,
            "macro_risk_off_score": self.macro_risk_off_score,
            "exit_ladder": ep,
            "require_smart_money": self.require_smart_money,
            "min_alpha_wallets": self.min_alpha_wallets,
        }


@dataclass
class Decision:
    action: Action
    reason: str
    pair: str | None = None
    score: float | None = None
    pnl_pct: float | None = None
    sell_fraction: float | None = None


def _slippage_pct(position_usd: float, liquidity_usd: float) -> float:
    if liquidity_usd <= 0:
        return 5.0
    return min(position_usd / liquidity_usd, 0.05) * 100


def round_trip_cost_pct(pair: Pair, position_usd: float) -> float:
    """Tek yön slippage ×2 + gidiş-dönüş gas (USD → %)."""
    slip = _slippage_pct(position_usd, pair.liquidity_usd) * 2
    gas_usd = 2 * GAS_COST_USD.get(pair.chain, 0.1)
    gas_pct = 100 * gas_usd / max(position_usd, 1.0)
    return round(slip + gas_pct, 2)


def expected_move_pct(pair: Pair, *, cex_hold_score: float = 0.0, trending_ok: bool = False) -> float:
    """Beklenen hareket — h1, m5, hacim ivmesi, CEX tut (Faz 8)."""
    h1 = max(pair.chg_h1, 0.0)
    m5 = pair.chg_m5 * 2.0 if pair.chg_m5 > 0 else 0.0
    vol_sp = (pair.vol_m5 * 12) / max(pair.vol_h1, 1.0)
    vol_move = min(vol_sp * 3.0, 8.0) if vol_sp >= 1.5 else 0.0
    cex_move = min(cex_hold_score / 10.0, 6.0) if cex_hold_score >= 45 else 0.0
    move = min(max(h1, m5, vol_move, cex_move), 25.0)
    if trending_ok:
        ds_move = min(max(pair.chg_h24, pair.chg_h1, 0.0) * 0.12, 18.0)
        move = max(move, ds_move)
    return move


def has_profit_edge(
    pair: Pair,
    position_usd: float,
    policy: DecisionPolicy,
    *,
    quote_slippage_pct: float = 0.0,
    cex_hold_score: float = 0.0,
    trending_ok: bool = False,
    genesis_ok: bool = False,
) -> tuple[bool, str]:
    cost = round_trip_cost_pct(pair, position_usd) + quote_slippage_pct
    move = expected_move_pct(pair, cex_hold_score=cex_hold_score, trending_ok=trending_ok or genesis_ok)
    need = cost + policy.min_edge_after_cost_pct
    if genesis_ok:
        need = cost + min(policy.min_edge_after_cost_pct, float(os.getenv("GENESIS_MIN_EDGE_PCT", "0.5")))
    if move < need:
        slip_note = f" + slip %{quote_slippage_pct:.1f}" if quote_slippage_pct else ""
        return False, f"kenar yetersiz (hareket ~%{move:.1f} < maliyet+min %{need:.1f}{slip_note})"
    slip_note = f" · slip %{quote_slippage_pct:.1f}" if quote_slippage_pct else ""
    return True, f"kenar OK (~%{move:.1f} vs min %{need:.1f}{slip_note})"


def evaluate_exit(
    pos: Position,
    price: float,
    score: float,
    missing_ticks: int,
    policy: DecisionPolicy,
    *,
    exit_policy: ExitPolicy | None = None,
    pair: Pair | None = None,
    exit_ctx: ExitContext | None = None,
) -> Decision | None:
    ep = exit_policy or policy.base_exit_policy()
    result = evaluate_exit_ladder(
        pos, price, score, missing_ticks, ep, pair, exit_ctx=exit_ctx
    )
    if result is None:
        return None
    if result.kind == "exit_partial":
        return Decision(
            "exit_partial",
            result.reason,
            pos.pair_name,
            score,
            result.pnl_pct,
            result.sell_fraction,
        )
    return Decision("exit", result.reason, pos.pair_name, score, result.pnl_pct)


def evaluate_entry(
    score: float,
    pair: Pair,
    position_usd: float,
    policy: DecisionPolicy,
    *,
    safety_ok: bool,
    kill_switch: bool,
    open_count: int,
    daily_pnl: float,
    daily_loss_limit: float,
    already_held: bool,
    live_allowed: bool,
    macro_avg: float | None = None,
    brain_penalty: float = 0.0,
    quote_slippage_pct: float = 0.0,
    smart_money_ok: bool = True,
    smart_money_note: str = "",
    cex_hold_score: float = 0.0,
    trending_ok: bool = False,
    genesis_ok: bool = False,
) -> Decision:
    if kill_switch:
        return Decision("skip", "kill-switch aktif", pair.name, score)
    if open_count >= policy.max_open_positions:
        return Decision("skip", "max pozisyon dolu", pair.name, score)
    if daily_pnl <= -daily_loss_limit:
        return Decision("skip", "günlük zarar limiti", pair.name, score)
    if already_held:
        return Decision("skip", "zaten açık", pair.name, score)
    if not live_allowed:
        return Decision("skip", "canlı ağ/key yok", pair.name, score)

    filter_ok, filter_note = token_filter_ok(pair, genesis_ok=genesis_ok)
    if not filter_ok:
        return Decision("skip", filter_note, pair.name, score)

    if pair.chg_h1 <= 0 and pair.chg_m5 <= 0 and cex_hold_score < 45 and not trending_ok:
        return Decision("skip", "momentum gate (h1/m5 negatif, CEX tut yok)", pair.name, score)

    chase_max = MAX_CHASE_H1_PCT
    if trending_ok or genesis_ok:
        chase_max = float(os.getenv("TRENDING_CHASE_H1_PCT", "120"))
    if pair.chg_h1 > chase_max and cex_hold_score < 55 and not trending_ok and not genesis_ok:
        return Decision(
            "skip",
            f"pump geç kalındı (h1 %{pair.chg_h1:.0f}>{chase_max:.0f}, CEX tut zayıf)",
            pair.name,
            score,
        )

    entry_min = policy.effective_entry_min(macro_avg, brain_penalty)
    if genesis_ok:
        entry_min = min(entry_min, float(os.getenv("GENESIS_ENTRY_MIN", "52")))
    if score < entry_min:
        extra = []
        if entry_min > policy.entry_score_min:
            extra.append("makro/brain risk-off")
        macro_note = f" (eşik {entry_min:.0f}" + (f", {', '.join(extra)})" if extra else ")")
        return Decision("skip", f"skor {score:.1f} < {entry_min:.0f}{macro_note}", pair.name, score)

    if pair.chg_h24 > float(os.getenv("LATE_PUMP_H24_PCT", "400")) and not genesis_ok:
        age_h = None
        if pair.pool_created_at:
            import time as _time

            age_h = (_time.time() - pair.pool_created_at) / 3600.0
        if age_h is None or age_h > float(os.getenv("LATE_PUMP_MAX_AGE_H", "8")):
            return Decision(
                "skip",
                f"tepe kaçırıldı (h24 %{pair.chg_h24:.0f}, yaş {age_h or 999:.0f}h)",
                pair.name,
                score,
            )

    if not safety_ok:
        return Decision("skip", "güvenlik RED", pair.name, score)

    if policy.require_smart_money and not smart_money_ok:
        return Decision("skip", smart_money_note or "smart money yok", pair.name, score)

    ok, edge_note = has_profit_edge(
        pair,
        position_usd,
        policy,
        quote_slippage_pct=quote_slippage_pct,
        cex_hold_score=cex_hold_score,
        trending_ok=trending_ok,
        genesis_ok=genesis_ok,
    )
    if not ok:
        return Decision("skip", edge_note, pair.name, score)

    sm = f" · {smart_money_note}" if smart_money_note else ""
    return Decision("enter", f"skor {score:.1f} · {edge_note}{sm}", pair.name, score)
