"""⚡500 çıkış — founder yarı sat kuralı."""

from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
from hibrit_trader.scanner import Pair


def test_boost500_partial_when_profit():
    pos = Position(
        pair_name="TRUAMP / SOL",
        chain="solana",
        token_address="T",
        pool_address="P",
        entry_price=1.0,
        amount_token=10.0,
        cost_usd=10.0,
        opened_at="t",
        entry_score=60.0,
        peak_price_usd=1.05,
    )
    pair = Pair(
        chain="solana",
        dex="raydium",
        pool_address="P",
        token_address="T",
        name="TRUAMP / SOL",
        price_usd=1.04,
        liquidity_usd=100_000,
        vol_m5=10_000,
        vol_h1=100_000,
        vol_h24=500_000,
        chg_m5=-1.0,
        chg_h1=-5.0,
        chg_h24=-90.0,
        txns_h1=1000,
        boost_score=500,
    )
    d = evaluate_exit_ladder(pos, 1.04, 50.0, 0, ExitPolicy(), pair)
    assert d is not None
    assert d.kind == "exit_partial"
    assert d.sell_fraction == 0.5
    assert "500" in d.reason


def test_boost500_partial_then_tighter_scratch():
    pos = Position(
        pair_name="X / SOL",
        chain="solana",
        token_address="T",
        pool_address="P",
        entry_price=1.0,
        amount_token=10.0,
        cost_usd=10.0,
        opened_at="t",
        entry_score=60.0,
        boost500_partial_done=True,
        tp1_done=True,
    )
    pair = Pair(
        chain="solana",
        dex="raydium",
        pool_address="P",
        token_address="T",
        name="X / SOL",
        price_usd=0.984,
        liquidity_usd=100_000,
        vol_m5=1_000,
        vol_h1=10_000,
        vol_h24=100_000,
        chg_m5=-1.5,
        chg_h1=-2.0,
        chg_h24=10.0,
        txns_h1=500,
        boost_score=500,
    )
    d = evaluate_exit_ladder(pos, 0.984, 50.0, 0, ExitPolicy(), pair)
    assert d is not None
    assert d.kind == "exit_full"
    assert "flash dump" in d.reason or "kalan" in d.reason
