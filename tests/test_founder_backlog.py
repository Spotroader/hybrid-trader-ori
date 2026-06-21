"""Founder backlog — watchlist demote, cooldown, fast path, scratch relax."""

import time

from hibrit_trader.dex_boost import watchlist_sort_key
from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
from hibrit_trader.pump_research import PumpProfile, founder_fast_entry_ok
from hibrit_trader.scanner import Pair
from hibrit_trader.session import Engine
from hibrit_trader.trade_confluence import (
    ConfluenceSnapshot,
    build_confluence_snapshot,
    compute_trade_confluence,
)


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="raydium",
        pool_address="P1",
        token_address="T1",
        name="YOUNG / SOL",
        price_usd=1.0,
        liquidity_usd=200_000,
        vol_m5=20_000,
        vol_h1=100_000,
        vol_h24=800_000,
        chg_m5=2.0,
        chg_h1=8.0,
        chg_h24=40.0,
        txns_h1=400,
        boost_score=50,
        pool_created_at=time.time() - 3600 * 2,
    )
    base.update(kw)
    return Pair(**base)


def test_watchlist_demotes_boost500():
    late = _pair(name="UPLON / SOL", boost_score=500, chg_h1=10.0)
    early = _pair(name="TREX / SOL", boost_score=50, chg_h1=15.0)
    ranked = [(84.0, late), (78.0, early)]
    ranked.sort(key=lambda x: watchlist_sort_key(x[0], x[1]))
    assert ranked[0][1].name.startswith("TREX")
    assert ranked[1][1].boost_score == 500


def test_founder_fast_entry_ok():
    pair = _pair(boost_score=50, chg_h1=5.0)
    pump = PumpProfile(
        moonshot_score=70,
        wallet_count=4,
        whale_signal=True,
        turnover=12.0,
        age_hours=2.0,
        trend_score=55.0,
    )
    assert founder_fast_entry_ok(pair, pump) is True
    assert founder_fast_entry_ok(_pair(boost_score=500, chg_h1=5.0), pump) is False


def test_founder_fast_relaxes_confluence(monkeypatch):
    monkeypatch.setenv("PAPER_AGGRESSIVE", "1")
    pair = _pair()
    snap = build_confluence_snapshot(
        binance_holds=[],
        okx_holds=[],
        whale_signals=[
            {
                "symbol": "YOUNG",
                "buy_signal": True,
                "score": 80,
                "wallet_count": 4,
            }
        ],
        brain_verdict=None,
        macro_avg=50.0,
        brain_penalty=0.0,
        confluence_min=55.0,
        min_layers=2,
        aggressive=True,
    )
    without = compute_trade_confluence(
        60.0, pair, snap, entry_min=50.0, smart_money_ok=True, founder_fast=False
    )
    with_fast = compute_trade_confluence(
        60.0, pair, snap, entry_min=50.0, smart_money_ok=True, founder_fast=True
    )
    assert with_fast.enter_ok or with_fast.score >= without.score
    assert "FAST" in with_fast.layer_labels


def test_young_pump_wider_scratch(monkeypatch):
    monkeypatch.setenv("FOUNDER_SCRATCH_RELAX", "1")
    monkeypatch.setenv("FOUNDER_SCRATCH_PCT", "-2.5")
    monkeypatch.setenv("SCRATCH_MIN_SEC", "0")
    monkeypatch.setenv("SCRATCH_HIGH_SCORE_MIN", "99")
    pos = Position(
        pair_name="Y / SOL",
        chain="solana",
        pool_address="P1",
        token_address="T1",
        entry_price=1.0,
        amount_token=10.0,
        cost_usd=10.0,
        entry_score=70.0,
        opened_at="t",
    )
    pair = _pair(pool_created_at=time.time() - 3600)
    ep = ExitPolicy(scratch_pct=-2.0)
    pos.opened_ts = time.time() - 120
    # -2.1% should NOT exit with relaxed -2.5 limit
    result = evaluate_exit_ladder(pos, 0.979, 60.0, 0, ep, pair)
    assert result is None
    result2 = evaluate_exit_ladder(pos, 0.974, 60.0, 0, ep, pair)
    assert result2 is not None
    assert "scratch" in result2.reason


def test_cooldown_after_winning_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_COOLDOWN_ANY_SEC", "3600")
    from hibrit_trader.pair_cooldown import PairCooldownStore

    store = PairCooldownStore(path=tmp_path / "cd.json")
    store.set_cooldown("TOK", "TREX / SOL", 3600)
    assert store.on_cooldown("TOK", "TREX / SOL") is True
    assert store.on_cooldown("OTHER", "TREX / SOL") is True  # symbol key
