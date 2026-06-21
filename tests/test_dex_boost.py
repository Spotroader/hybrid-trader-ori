"""Dex boost giriş ayarı — founder ⚡500 geç kuralı."""

from hibrit_trader.dex_boost import dex_boost_entry_adjustment, watchlist_sort_key
from hibrit_trader.scanner import Pair


def test_boost_500_penalized():
    assert dex_boost_entry_adjustment(500) == -12.0
    assert dex_boost_entry_adjustment(530) == -12.0


def test_boost_erken_bonus():
    assert dex_boost_entry_adjustment(50) == 8.0
    assert dex_boost_entry_adjustment(150) == 2.0


def test_watchlist_demotes_boost500():
    late = Pair(
        chain="solana", dex="x", pool_address="a", token_address="a",
        name="L/SOL", price_usd=1, liquidity_usd=50_000,
        vol_m5=1, vol_h1=1, vol_h24=1, chg_m5=1, chg_h1=1, chg_h24=1, txns_h1=1,
        boost_score=500,
    )
    early = Pair(
        chain="solana", dex="x", pool_address="b", token_address="b",
        name="E/SOL", price_usd=1, liquidity_usd=50_000,
        vol_m5=1, vol_h1=1, vol_h24=1, chg_m5=1, chg_h1=1, chg_h24=1, txns_h1=1,
        boost_score=50,
    )
    assert watchlist_sort_key(90.0, late) > watchlist_sort_key(80.0, early)


def test_boost_sifir():
    assert dex_boost_entry_adjustment(0) == 0.0
