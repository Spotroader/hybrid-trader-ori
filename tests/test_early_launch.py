"""Erken launch — genesis skor ve havuz seçimi."""

import time

from hibrit_trader.early_launch import (
    classify_pump_window,
    genesis_entry_ok,
    genesis_score,
    is_trending_late_pump,
    select_entry_pool,
)
from hibrit_trader.scanner import Pair


def _young_hot(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="meteora",
        pool_address="PNEW",
        token_address="TNEW",
        name="MERLIN / SOL",
        price_usd=0.00005,
        liquidity_usd=45_000,
        vol_m5=12_000,
        vol_h1=80_000,
        vol_h24=200_000,
        chg_m5=8.0,
        chg_h1=35.0,
        chg_h24=120.0,
        txns_h1=400,
        txns_m5=28,
        pool_created_at=time.time() - 3600 * 2.5,
        boost_score=30,
    )
    base.update(kw)
    return Pair(**base)


def _late_parabolic(**kw) -> Pair:
    return _young_hot(
        chg_h1=272000,
        chg_h24=278000,
        chg_m5=-8.0,
        price_usd=0.00103,
        liquidity_usd=95_000,
        **kw,
    )


def test_genesis_scores_young_momentum():
    p = _young_hot()
    g = genesis_score(p)
    assert g >= 52
    ok, note = genesis_entry_ok(p)
    assert ok
    assert "genesis" in note


def test_genesis_rejects_parabolic_h1():
    p = _late_parabolic()
    assert genesis_score(p) == 0.0
    assert not genesis_entry_ok(p)[0]


def test_trending_late_class_merlin_and_chaton():
    """DexScreener trending sınıfı — parabolik h1 veya h24 geç pump."""
    assert is_trending_late_pump(_late_parabolic())
    chaton = _young_hot(
        name="Chaton / SOL",
        chg_h1=-11.0,
        chg_h24=2268.0,
        pool_created_at=time.time() - 3600 * 23.5,
    )
    assert is_trending_late_pump(chaton)
    pw = classify_pump_window(chaton)
    assert pw["window"] == "trending_late"
    assert pw["action"] == "avoid"

    loop_genesis = _young_hot(
        name="LOOP / SOL",
        chg_h1=3.7,
        chg_h24=3.7,
        pool_created_at=time.time() - 60,
        txns_m5=18,
        vol_m5=8000,
    )
    pw2 = classify_pump_window(loop_genesis)
    assert pw2["window"] in ("genesis", "early")
    import time as _time

    young_item = {
        "chainId": "solana",
        "dexId": "meteora",
        "pairAddress": "YOUNG",
        "baseToken": {"address": "T1", "symbol": "M"},
        "quoteToken": {"symbol": "SOL"},
        "priceUsd": "0.00005",
        "liquidity": {"usd": 40000},
        "volume": {"m5": 15000, "h1": 90000, "h24": 200000},
        "priceChange": {"m5": 10, "h1": 40, "h24": 80},
        "txns": {"m5": {"buys": 20, "sells": 8}, "h1": {"buys": 100, "sells": 80}},
        "pairCreatedAt": int((_time.time() - 7200) * 1000),
    }
    old_item = {
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": "OLD",
        "baseToken": {"address": "T1", "symbol": "M"},
        "quoteToken": {"symbol": "SOL"},
        "priceUsd": "0.001",
        "liquidity": {"usd": 95000},
        "volume": {"m5": 1500, "h1": 40000, "h24": 1600000},
        "priceChange": {"m5": -2, "h1": 11, "h24": 278},
        "txns": {"m5": {"buys": 13, "sells": 23}, "h1": {"buys": 279, "sells": 280}},
        "pairCreatedAt": int((_time.time() - 86400 * 4) * 1000),
    }
    picked = select_entry_pool([old_item, young_item])
    assert picked is not None
    assert picked.pool_address == "YOUNG"
