"""Pump.fun feed + genesis bonus tests."""

import time

from hibrit_trader.early_launch import genesis_score
from hibrit_trader.pump_fun_feed import is_pump_fun_mint, pump_fun_genesis_bonus, reset_seen_for_tests
from hibrit_trader.scanner import Pair


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="pumpswap",
        pool_address="P1",
        token_address="AvxFBjWydMYWD7C8pHzSkGxNYAFWr7aNBbAKm84bpump",
        name="TEST / SOL",
        price_usd=0.0001,
        liquidity_usd=20_000,
        vol_m5=5000,
        vol_h1=30_000,
        vol_h24=80_000,
        chg_m5=6,
        chg_h1=18,
        chg_h24=40,
        txns_h1=200,
        txns_m5=20,
        pool_created_at=time.time() - 3600,
        discovery_source="pump_fun",
    )
    base.update(kw)
    return Pair(**base)


def test_is_pump_fun_mint_suffix():
    assert is_pump_fun_mint("AvxFBjWydMYWD7C8pHzSkGxNYAFWr7aNBbAKm84bpump")
    assert not is_pump_fun_mint("So11111111111111111111111111111111111111112")


def test_pump_fun_genesis_bonus(monkeypatch):
    monkeypatch.setenv("PUMP_FUN_GENESIS_BONUS", "15")
    p = _pair()
    base = genesis_score(Pair(**{**p.__dict__, "discovery_source": ""}))
    boosted = genesis_score(p)
    assert boosted >= base + pump_fun_genesis_bonus() - 0.1


def test_reset_seen_for_tests():
    reset_seen_for_tests()
