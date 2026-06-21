"""Peak exit — dinamik tepe intel + 5m dump."""

import os

import pytest

from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
from hibrit_trader.peak_intelligence import ExitContext
from hibrit_trader.scanner import Pair


@pytest.fixture(autouse=True)
def _dynamic_peak(monkeypatch):
    monkeypatch.setenv("DYNAMIC_PEAK_EXIT", "1")
    monkeypatch.setenv("PEAK_EXIT_FAST", "1")


def test_peak_5m_dump_exit():
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    pos = Position(
        pair_name="HAPPY / SOL",
        chain="solana",
        token_address="T",
        pool_address="P",
        entry_price=1.0,
        amount_token=18.0,
        cost_usd=18.0,
        opened_at="t",
        entry_score=70.0,
        peak_price_usd=1.15,
        initial_amount_token=18.0,
    )
    pair = Pair(
        chain="solana",
        dex="raydium",
        pool_address="P",
        token_address="T",
        name="HAPPY / SOL",
        price_usd=1.12,
        liquidity_usd=79_000,
        vol_m5=400_000,
        vol_h1=2_000_000,
        vol_h24=5_600_000,
        chg_m5=-8.0,
        chg_h1=30.0,
        chg_h24=500.0,
        txns_h1=5000,
    )
    ctx = ExitContext(dex_score=50.0, whale={"buy_signal": False})
    d = evaluate_exit_ladder(pos, 1.12, 50.0, 0, ep, pair, exit_ctx=ctx)
    assert d is not None
    assert d.kind == "exit_full"
    assert "peak" in d.reason.lower() or "intel" in d.reason.lower()


def test_dynamic_peak_no_fixed_tp():
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    assert ep.tp1_pct >= 9999


def test_meme_winner_peak_intel_partial():
    """SPCX benzeri — yüksek kâr + momentum dönüşü → kısmi sat, sabit +18% yok."""
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    entry = 0.00055138
    price = 0.00220037
    pnl = (price - entry) / entry * 100
    assert pnl > 200

    pos = Position(
        pair_name="SPCX69 / SOL",
        chain="solana",
        token_address="T",
        pool_address="P",
        entry_price=entry,
        amount_token=15_000.0,
        cost_usd=8.5,
        opened_at="t",
        entry_score=72.0,
        peak_price_usd=price,
        initial_amount_token=15_000.0,
    )
    pair = Pair(
        chain="solana",
        dex="raydium",
        pool_address="P",
        token_address="T",
        name="SPCX69 / SOL",
        price_usd=price,
        liquidity_usd=120_000,
        vol_m5=50_000,
        vol_h1=800_000,
        vol_h24=3_000_000,
        chg_m5=-5.5,
        chg_h1=35.0,
        chg_h24=400.0,
        txns_h1=4000,
    )
    ctx = ExitContext(
        dex_score=55.0,
        fear_greed=78,
        exit_bias="neutral",
        whale={"symbol": "SPCX69", "buy_signal": False},
    )
    d = evaluate_exit_ladder(pos, price, 55.0, 0, ep, pair, exit_ctx=ctx)
    assert d is not None
    assert d.kind in ("exit_partial", "exit_full")
    assert "tp1" not in d.reason.lower()
    assert "18%" not in d.reason
