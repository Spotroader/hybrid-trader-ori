"""Runner giriş — SIN sınıfı (6–24h, h1/m5 sıcak, genesis dışı)."""

import time

from hibrit_trader.early_launch import pump_entry_ok, runner_entry_ok
from hibrit_trader.scanner import Pair


def _sin_like() -> Pair:
    now = time.time()
    return Pair(
        name="SIN / SOL",
        chain="solana",
        dex="pumpswap",
        token_address="sin" + "x" * 40,
        pool_address="pool" + "x" * 36,
        price_usd=0.00008,
        liquidity_usd=22_000,
        vol_m5=50_000,
        vol_h1=200_000,
        vol_h24=500_000,
        txns_m5=80,
        txns_h1=400,
        chg_m5=12.0,
        chg_h1=25.0,
        chg_h24=180.0,
        pool_created_at=now - 13.7 * 3600,
    )


def test_runner_ok_sin_class():
    ok, note = runner_entry_ok(_sin_like())
    assert ok, note
    assert note.startswith("runner")


def test_pump_entry_prefers_genesis_or_runner():
    ok, note = pump_entry_ok(_sin_like())
    assert ok
    assert "runner" in note or "genesis" in note
