"""Moonshot / pump profili testleri."""

import time

from hibrit_trader.pump_research import analyze_pump_pair
from hibrit_trader.scanner import Pair


def _xp_like_pair() -> Pair:
    return Pair(
        chain="solana",
        dex="raydium",
        name="XP / SOL",
        token_address="XP1",
        pool_address="POOL_XP",
        price_usd=0.001,
        liquidity_usd=31_000,
        vol_m5=50_000,
        vol_h1=400_000,
        vol_h24=1_400_000,
        chg_m5=11.9,
        chg_h1=11.9,
        chg_h24=766.0,
        txns_h1=5000,
        txns_h24=24_599,
        boost_score=10,
        pool_created_at=time.time() - 12 * 3600,
        market_cap_usd=155_000,
    )


def test_moonshot_yuksek_h24_genç_havuz():
    p = analyze_pump_pair(_xp_like_pair(), wallet_count=3)
    assert p.moonshot_score >= 62
    assert p.turnover > 10
    assert p.age_hours is not None and p.age_hours <= 24


def test_moonshot_dusuk_hacim_dusuk():
    cold = _xp_like_pair()
    cold.chg_h24 = 2.0
    cold.vol_h24 = 1000
    cold.boost_score = 0
    p = analyze_pump_pair(cold, wallet_count=0)
    assert p.moonshot_score < 50
