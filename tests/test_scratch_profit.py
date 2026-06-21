"""Scratch v2 — geniş eşik, min hold, theta derin zarar (para odaklı)."""

import time

from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
from hibrit_trader.scanner import Pair


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="raydium",
        pool_address="P1",
        token_address="T1",
        name="MEME / SOL",
        price_usd=1.0,
        liquidity_usd=200_000,
        vol_m5=20_000,
        vol_h1=100_000,
        vol_h24=800_000,
        chg_m5=3.0,
        chg_h1=12.0,
        chg_h24=25.0,
        txns_h1=300,
        boost_score=50,
        pool_created_at=time.time() - 3600 * 3,
    )
    base.update(kw)
    return Pair(**base)


def _pos(**kw) -> Position:
    base = dict(
        pair_name="MEME / SOL",
        chain="solana",
        pool_address="P1",
        token_address="T1",
        entry_price=1.0,
        amount_token=10.0,
        cost_usd=10.0,
        entry_score=70.0,
        opened_at="t",
        opened_ts=time.time() - 30,
    )
    base.update(kw)
    return Position(**base)


def test_scratch_grace_blocks_early_cut(monkeypatch):
    monkeypatch.setenv("SCRATCH_MIN_SEC", "90")
    monkeypatch.setenv("FOUNDER_SCRATCH_PCT", "-5.5")
    pos = _pos(opened_ts=time.time() - 30)
    pair = _pair()
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    # −4% — eski −3% scratch'ta kesilirdi; grace + geniş eşik tutar
    assert evaluate_exit_ladder(pos, 0.96, 60.0, 0, ep, pair) is None


def test_scratch_fires_after_grace(monkeypatch):
    monkeypatch.setenv("SCRATCH_MIN_SEC", "90")
    monkeypatch.setenv("FOUNDER_SCRATCH_PCT", "-5.5")
    pos = _pos(opened_ts=time.time() - 120)
    pair = _pair()
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    d = evaluate_exit_ladder(pos, 0.92, 60.0, 0, ep, pair)
    assert d is not None
    assert "scratch" in d.reason


def test_scratch_flash_bypasses_grace(monkeypatch):
    monkeypatch.setenv("SCRATCH_MIN_SEC", "90")
    monkeypatch.setenv("SCRATCH_FLASH_PCT", "-10.0")
    pos = _pos(opened_ts=time.time() - 10)
    pair = _pair()
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    d = evaluate_exit_ladder(pos, 0.89, 60.0, 0, ep, pair)
    assert d is not None
    assert "flash" in d.reason


def test_theta_deep_loss_before_20min(monkeypatch):
    monkeypatch.setenv("THETA_FLOOR_PCT", "-4.0")
    monkeypatch.setenv("THETA_DEEP_SEC", "600")
    pos = _pos(opened_ts=time.time() - 650)
    ep = ExitPolicy.for_dex_trending(ExitPolicy())
    d = evaluate_exit_ladder(pos, 0.92, 60.0, 0, ep, _pair())
    assert d is not None
    assert "theta derin" in d.reason
