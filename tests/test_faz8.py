"""Faz 8 — CEX confluence, skor kalibrasyonu, giriş teşhisi."""

from hibrit_trader.cex_confluence import (
    cex_boost_points,
    cex_symbol_scores,
    pair_base_symbol,
)
from hibrit_trader.decision import DecisionPolicy, evaluate_entry, has_profit_edge
from hibrit_trader.entry_diagnostics import diagnose_pair
from hibrit_trader.scanner import Pair
from hibrit_trader.score import opportunity_score, rank


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="raydium",
        pool_address="P1",
        token_address="T1",
        name="CARDS / USDC",
        price_usd=1.0,
        liquidity_usd=200_000,
        vol_m5=20_000,
        vol_h1=100_000,
        vol_h24=800_000,
        chg_m5=3.0,
        chg_h1=12.0,
        chg_h24=25.0,
        txns_h1=300,
    )
    base.update(kw)
    return Pair(**base)


def test_pair_base_symbol_strips_fee_suffix():
    assert pair_base_symbol(_pair(name="VELVET / USDC 0.01%")) == "VELVET"


def test_cex_boost_high_hold():
    scores = {"CARDS": 72.0}
    boost, sym = cex_boost_points(_pair(), scores)
    assert sym == "CARDS"
    assert boost == 12.0


def test_rank_applies_cex_boost():
    p = _pair()
    plain = rank([p], cex_scores=None)
    boosted = rank([p], cex_scores={"CARDS": 70.0})
    assert boosted[0][0] > plain[0][0]


def test_pump_penalty_softer_than_before():
    moderate = opportunity_score(_pair(chg_h1=25))
    extreme = opportunity_score(_pair(chg_h1=90))
    assert moderate > 0
    assert moderate > extreme


def test_negative_h1_not_zero_score():
    s = opportunity_score(_pair(chg_h1=-2.0, chg_m5=0))
    assert s > 0


def test_edge_uses_vol_momentum_when_h1_low():
    policy = DecisionPolicy(min_edge_after_cost_pct=4.0)
    pair = _pair(chg_h1=1.0, chg_m5=4.0, vol_m5=30_000, vol_h1=50_000)
    ok, _ = has_profit_edge(pair, 15.0, policy)
    assert ok


def test_momentum_gate_blocks_flat_negative():
    policy = DecisionPolicy(require_smart_money=False)
    pair = _pair(chg_h1=-3.0, chg_m5=-1.0)
    d = evaluate_entry(
        70.0,
        pair,
        15.0,
        policy,
        safety_ok=True,
        kill_switch=False,
        open_count=0,
        daily_pnl=0.0,
        daily_loss_limit=30.0,
        already_held=False,
        live_allowed=True,
        cex_hold_score=0.0,
    )
    assert d.action == "skip"
    assert "momentum gate" in d.reason


def test_cex_hold_bypasses_momentum_gate():
    policy = DecisionPolicy(require_smart_money=False)
    pair = _pair(chg_h1=-3.0, chg_m5=-1.0)
    d = evaluate_entry(
        70.0,
        pair,
        15.0,
        policy,
        safety_ok=True,
        kill_switch=False,
        open_count=0,
        daily_pnl=0.0,
        daily_loss_limit=30.0,
        already_held=False,
        live_allowed=True,
        cex_hold_score=55.0,
    )
    assert d.action == "enter"


def test_diagnose_pair_structure():
    policy = DecisionPolicy(require_smart_money=False)
    row = diagnose_pair(
        68.0,
        _pair(),
        policy=policy,
        position_usd=15.0,
        macro_avg=None,
        brain_penalty=0.0,
        cex_scores=cex_symbol_scores(
            [{"symbol": "CARDS", "score": 70}],
            [],
        ),
        safety=None,
        smart_money_ok=True,
        smart_money_note="ok",
        kill_switch=False,
        open_count=0,
        max_open=3,
        daily_pnl=0.0,
        daily_loss_limit=15.0,
        already_held=False,
        live_allowed=True,
    )
    assert "gates" in row
    assert row["blocker"] == "güvenlik bekleniyor"
    assert row["gates"]["score"]["cex_boost"] == 12.0
