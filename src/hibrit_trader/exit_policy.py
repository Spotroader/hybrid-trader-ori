"""Katmanlı çıkış motoru — scratch, ATR stop, kademeli TP, trail, theta, peak dump."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal

from hibrit_trader.paper import Position
from hibrit_trader.peak_intelligence import ExitContext, dynamic_peak_enabled, evaluate_peak_intelligence
from hibrit_trader.dex_trending_strategy import pool_age_hours
from hibrit_trader.scanner import Pair

ExitKind = Literal["hold", "exit_full", "exit_partial"]


@dataclass
class ExitPolicy:
    scratch_pct: float = -2.0
    stop_loss_pct: float = -8.0
    breakeven_trigger_pct: float = 8.0
    runner_arm_pct: float = 20.0
    runner_trail_pct: float = 12.0
    tp1_pct: float = 45.0
    tp1_sell_frac: float = 0.25
    tp2_pct: float = 65.0
    tp2_sell_frac: float = 0.35
    trail_pct: float = 15.0
    theta_sec: float = 1200.0
    theta_min_profit_pct: float = 8.0
    atr_widen_cap_pct: float = 7.0
    chandelier_mult: float = 3.0
    exit_score_max: float = 45.0
    missing_ticks_exit: int = 3

    def summary(self) -> dict:
        return {
            "scratch_pct": self.scratch_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "breakeven_trigger_pct": self.breakeven_trigger_pct,
            "runner_arm_pct": self.runner_arm_pct,
            "runner_trail_pct": self.runner_trail_pct,
            "chandelier_mult": self.chandelier_mult,
            "tp1_pct": self.tp1_pct,
            "tp1_sell_frac": self.tp1_sell_frac,
            "tp2_pct": self.tp2_pct,
            "tp2_sell_frac": self.tp2_sell_frac,
            "trail_pct": self.trail_pct,
            "theta_sec": self.theta_sec,
            "theta_min_profit_pct": self.theta_min_profit_pct,
        }

    @classmethod
    def for_regime(cls, base: ExitPolicy, action_bias: str) -> ExitPolicy:
        if action_bias == "aggressive":
            return replace(
                base,
                scratch_pct=-5.0,
                runner_arm_pct=18.0,
                runner_trail_pct=10.0,
                trail_pct=18.0,
                tp1_pct=50.0,
                tp1_sell_frac=0.20,
                tp2_pct=80.0,
                stop_loss_pct=-10.0,
                theta_min_profit_pct=10.0,
            )
        if action_bias == "defensive":
            return replace(
                base,
                scratch_pct=-1.5,
                runner_arm_pct=22.0,
                runner_trail_pct=8.0,
                trail_pct=10.0,
                stop_loss_pct=-6.0,
                theta_sec=900.0,
                theta_min_profit_pct=5.0,
            )
        return base

    @classmethod
    def for_dex_trending(cls, base: ExitPolicy) -> ExitPolicy:
        """Meme/DEX — dinamik peak intel; sabit TP kapalı."""
        scratch = base.scratch_pct
        if os.getenv("FOUNDER_SCRATCH_RELAX", "1") != "0":
            scratch = min(scratch, float(os.getenv("FOUNDER_SCRATCH_PCT", "-5.5")))
        ep = replace(
            base,
            scratch_pct=scratch,
            breakeven_trigger_pct=4.0,
            runner_arm_pct=5.0,
            runner_trail_pct=6.0,
            trail_pct=8.0,
            chandelier_mult=2.0,
            theta_min_profit_pct=6.0,
        )
        if dynamic_peak_enabled():
            ep = replace(ep, tp1_pct=9999.0, tp2_pct=9999.0)
        else:
            ep = replace(
                ep,
                tp1_pct=18.0,
                tp1_sell_frac=0.40,
                tp2_pct=32.0,
                tp2_sell_frac=0.35,
            )
        return ep


def peak_exit_enabled() -> bool:
    return os.getenv("PEAK_EXIT_FAST", "1") != "0"


def _uses_dynamic_peak(ep: ExitPolicy) -> bool:
    return dynamic_peak_enabled() and ep.tp1_pct >= 9000


def _peak_momentum_exit(
    pair: Pair | None,
    pnl: float,
    peak_drawdown_pct: float,
) -> ExitDecision | None:
    """5m dump veya peak'ten sıkı geri çekilme — kârdayken tam çık."""
    if not peak_exit_enabled() or pair is None:
        return None
    min_pnl = float(os.getenv("PEAK_EXIT_MIN_PNL", "6"))
    if pnl < min_pnl:
        return None
    dump_m5 = float(os.getenv("PEAK_EXIT_M5_PCT", "-5"))
    if pair.chg_m5 <= dump_m5:
        return ExitDecision(
            "exit_full",
            f"peak 5m dump %{pair.chg_m5:.1f}",
            1.0,
            pnl,
        )
    tight = float(os.getenv("PEAK_TRAIL_PCT", "5"))
    if pnl >= float(os.getenv("PEAK_TRAIL_ARM_PNL", "10")) and peak_drawdown_pct >= tight and pair.chg_m5 < 0:
        return ExitDecision(
            "exit_full",
            f"peak trail -{peak_drawdown_pct:.1f}%",
            1.0,
            pnl,
        )
    return None


@dataclass
class ExitDecision:
    kind: ExitKind
    reason: str
    sell_fraction: float = 1.0
    pnl_pct: float = 0.0


def _pnl_pct(pos: Position, price: float) -> float:
    if pos.entry_price <= 0:
        return 0.0
    return (price - pos.entry_price) / pos.entry_price * 100


def _position_age_sec(pos: Position) -> float:
    if pos.opened_ts > 0:
        return time.time() - pos.opened_ts
    try:
        opened = datetime.fromisoformat(pos.opened_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - opened).total_seconds()
    except (ValueError, TypeError):
        return 0.0


def _atr_widen_pct(pair: Pair | None, cap: float) -> float:
    if pair is None:
        return 0.0
    vol_proxy = min(abs(pair.chg_h1) * 0.35 + abs(pair.chg_m5) * 0.15, cap)
    return vol_proxy


def _effective_stop(exit_policy: ExitPolicy, pair: Pair | None) -> float:
    widen = _atr_widen_pct(pair, exit_policy.atr_widen_cap_pct)
    return exit_policy.stop_loss_pct - widen


def _chandelier_stop_price(pos: Position, exit_policy: ExitPolicy) -> float | None:
    """Chandelier long stop = peak - ATR%×mult (runner modda)."""
    if pos.peak_price_usd <= 0:
        return None
    atr_pct = pos.atr_pct_at_entry if pos.atr_pct_at_entry > 0 else 8.0
    drop_pct = min(atr_pct * exit_policy.chandelier_mult, 28.0)
    return pos.peak_price_usd * (1 - drop_pct / 100)


def init_position_exit_state(pos: Position, pair: Pair | None = None) -> None:
    if pos.peak_price_usd <= 0:
        pos.peak_price_usd = pos.entry_price
    if pos.initial_amount_token <= 0:
        pos.initial_amount_token = pos.amount_token
    if pos.opened_ts <= 0:
        pos.opened_ts = time.time()
    if pair is not None and pos.atr_pct_at_entry <= 0:
        pos.atr_pct_at_entry = _atr_widen_pct(pair, 12.0)


def update_position_mark(pos: Position, price: float) -> None:
    if price > pos.peak_price_usd:
        pos.peak_price_usd = price


def _is_runner_momentum(pair: Pair) -> bool:
    return pair.chg_h1 >= float(os.getenv("RUNNER_MIN_H1", "15")) and pair.chg_m5 >= float(
        os.getenv("RUNNER_MIN_M5", "5")
    )


def _scratch_limit(exit_policy: ExitPolicy, pos: Position, pair: Pair | None) -> float:
    """Negatif eşik — daha negatif = daha geniş (meme volatilitesine nefes)."""
    scratch_lim = exit_policy.scratch_pct
    if pos.boost500_partial_done:
        # Daraltma -2.0 tabani nedeniyle fiilen etkisiz (varsayilan scratch da -2.0); bilinclidir, degistirmeden once POLICY.md'ye bak.
        scratch_lim = max(scratch_lim, -2.0)
    if pair is None or os.getenv("FOUNDER_SCRATCH_RELAX", "1") == "0":
        return scratch_lim

    if _is_runner_momentum(pair):
        scratch_lim = min(scratch_lim, float(os.getenv("RUNNER_SCRATCH_PCT", "-7.0")))

    high_score_min = float(os.getenv("SCRATCH_HIGH_SCORE_MIN", "68"))
    if pos.entry_score >= high_score_min:
        scratch_lim = min(scratch_lim, float(os.getenv("SCRATCH_MOMENTUM_PCT", "-7.0")))
    elif pair.chg_h1 >= float(os.getenv("SCRATCH_WARM_H1", "10")):
        scratch_lim = min(scratch_lim, float(os.getenv("SCRATCH_WARM_PCT", "-6.0")))

    boost = int(getattr(pair, "boost_score", 0) or 0)
    if boost >= 500:
        return scratch_lim

    age = pool_age_hours(pair)
    max_age = float(os.getenv("FOUNDER_SCRATCH_MAX_AGE_HOURS", "24"))
    if age is not None and age <= max_age and boost < 500:
        scratch_lim = min(scratch_lim, float(os.getenv("FOUNDER_SCRATCH_PCT", "-5.5")))

    if getattr(pair, "discovery_source", "") == "pump_fun":
        scratch_lim = min(scratch_lim, float(os.getenv("PUMP_FUN_SCRATCH_PCT", "-9.0")))

    return scratch_lim


def _scratch_min_hold_sec(pos: Position, pair: Pair | None) -> int:
    if pair is None:
        return 0
    hold = int(os.getenv("SCRATCH_MIN_SEC", "90"))
    if _is_runner_momentum(pair):
        hold = max(hold, int(os.getenv("RUNNER_SCRATCH_MIN_SEC", "120")))
    if getattr(pair, "discovery_source", "") == "pump_fun":
        hold = max(hold, int(os.getenv("PUMP_FUN_SCRATCH_MIN_SEC", "180")))
    if pos.entry_score >= float(os.getenv("SCRATCH_HIGH_SCORE_MIN", "68")):
        hold += int(os.getenv("SCRATCH_HIGH_SCORE_GRACE_SEC", "30"))
    return hold


def _evaluate_scratch(
    pos: Position,
    price: float,
    pnl: float,
    exit_policy: ExitPolicy,
    pair: Pair | None,
) -> ExitDecision | None:
    flash_pct = float(os.getenv("SCRATCH_FLASH_PCT", "-10.0"))
    if pnl <= flash_pct:
        tag = "flash dump — kalan sat" if pos.boost500_partial_done else f"scratch flash {flash_pct:.1f}%"
        return ExitDecision("exit_full", tag, 1.0, pnl)

    scratch_lim = _scratch_limit(exit_policy, pos, pair)
    if pnl > scratch_lim:
        return None

    hold = _position_age_sec(pos)
    min_hold = _scratch_min_hold_sec(pos, pair)
    if hold < min_hold:
        return None

    reason = "flash dump — kalan sat" if pos.boost500_partial_done else f"scratch {scratch_lim:.1f}%"
    return ExitDecision("exit_full", reason, 1.0, pnl)


def _evaluate_theta(pos: Position, pnl: float, exit_policy: ExitPolicy) -> ExitDecision | None:
    age = _position_age_sec(pos)
    floor = float(os.getenv("THETA_FLOOR_PCT", "-4.0"))
    deep_sec = int(os.getenv("THETA_DEEP_SEC", "600"))

    if age >= deep_sec and pnl <= floor:
        return ExitDecision("exit_full", f"theta derin zarar {pnl:.1f}%", 1.0, pnl)

    if age >= exit_policy.theta_sec and floor < pnl < exit_policy.theta_min_profit_pct:
        return ExitDecision(
            "exit_full",
            f"theta durgun {pnl:.1f}% (<{exit_policy.theta_min_profit_pct:.0f}% hedef)",
            1.0,
            pnl,
        )
    return None


def evaluate_exit_ladder(
    pos: Position,
    price: float,
    score: float,
    missing_ticks: int,
    exit_policy: ExitPolicy,
    pair: Pair | None = None,
    exit_ctx: ExitContext | None = None,
) -> ExitDecision | None:
    """Pozisyon durumunu günceller; çıkış/kısmi sat kararı döner."""
    update_position_mark(pos, price)
    pnl = _pnl_pct(pos, price)

    if missing_ticks >= exit_policy.missing_ticks_exit:
        return ExitDecision("exit_full", "veri kayboldu", 1.0, pnl)

    theta_exit = _evaluate_theta(pos, pnl, exit_policy)
    if theta_exit:
        return theta_exit

    if pair is not None and not pos.boost500_partial_done:
        bs = int(getattr(pair, "boost_score", 0) or 0)
        if bs >= 500 and pnl > 0:
            pos.boost500_partial_done = True
            pos.tp1_done = True
            return ExitDecision("exit_partial", "⚡500 geç — yarı sat", 0.5, pnl)

    scratch_exit = _evaluate_scratch(pos, price, pnl, exit_policy, pair)
    if scratch_exit:
        return scratch_exit

    eff_stop = _effective_stop(exit_policy, pair)
    if pnl <= eff_stop:
        return ExitDecision("exit_full", f"stop {eff_stop:.1f}%", 1.0, pnl)

    if pnl >= exit_policy.breakeven_trigger_pct:
        pos.breakeven_armed = True

    if pos.breakeven_armed and pnl <= 0.5:
        return ExitDecision("exit_full", "break-even stop", 1.0, pnl)

    peak_dd = (
        (pos.peak_price_usd - price) / pos.peak_price_usd * 100
        if pos.peak_price_usd > 0
        else 0.0
    )

    if pair is not None and _uses_dynamic_peak(exit_policy):
        ctx = exit_ctx or ExitContext()
        ctx.dex_score = score
        intel = evaluate_peak_intelligence(pos, pair, pnl, peak_dd, ctx)
        if intel:
            if intel.exit_full:
                return ExitDecision("exit_full", intel.reason, 1.0, pnl)
            if intel.exit_partial:
                if not pos.tp1_done:
                    pos.tp1_done = True
                else:
                    pos.tp2_done = True
                pos.trail_armed = True
                pos.runner_mode = True
                return ExitDecision(
                    "exit_partial",
                    intel.reason,
                    intel.sell_fraction,
                    pnl,
                )

    peak_exit = _peak_momentum_exit(pair, pnl, peak_dd)
    if peak_exit:
        return peak_exit

    # Runner — kârda erken trail (sabit TP yok)
    if pnl + 0.05 >= exit_policy.runner_arm_pct and not pos.trail_armed:
        pos.trail_armed = True
        pos.runner_mode = True

    if not _uses_dynamic_peak(exit_policy):
        if not pos.tp1_done and pnl >= exit_policy.tp1_pct:
            pos.tp1_done = True
            frac = exit_policy.tp1_sell_frac
            return ExitDecision(
                "exit_partial",
                f"tp1 +{exit_policy.tp1_pct:.0f}% (%{frac * 100:.0f} sat)",
                frac,
                pnl,
            )

        if not pos.tp2_done and pnl >= exit_policy.tp2_pct:
            pos.tp2_done = True
            pos.trail_armed = True
            frac = exit_policy.tp2_sell_frac
            return ExitDecision(
                "exit_partial",
                f"tp2 +{exit_policy.tp2_pct:.0f}% (%{frac * 100:.0f} sat)",
                frac,
                pnl,
            )

    if pos.trail_armed and pos.peak_price_usd > 0:
        drawdown = (pos.peak_price_usd - price) / pos.peak_price_usd * 100
        trail_pct = exit_policy.runner_trail_pct if getattr(pos, "runner_mode", False) else exit_policy.trail_pct
        if getattr(pos, "runner_mode", False) and pos.atr_pct_at_entry > 0:
            trail_pct = max(trail_pct, min(pos.atr_pct_at_entry * 1.8, 22.0))

        if getattr(pos, "runner_mode", False):
            from hibrit_trader.peak_intelligence import _adaptive_peak_trail_pct

            trail_pct = min(trail_pct, _adaptive_peak_trail_pct(pnl))
            ce_stop = _chandelier_stop_price(pos, exit_policy)
            if ce_stop and price <= ce_stop and pnl > 0:
                return ExitDecision(
                    "exit_full",
                    f"chandelier -{drawdown:.1f}% peak",
                    1.0,
                    pnl,
                )

        if drawdown >= trail_pct:
            tag = "runner trail" if getattr(pos, "runner_mode", False) else "trail"
            return ExitDecision("exit_full", f"{tag} -{trail_pct:.0f}%", 1.0, pnl)

    # Skor düşüşü: yalnız kâr yok / durgun pozisyon — kârda TP/trail yönetsin
    if score < exit_policy.exit_score_max and pnl < exit_policy.theta_min_profit_pct:
        return ExitDecision("exit_full", "fırsat bitti", 1.0, pnl)

    return None
