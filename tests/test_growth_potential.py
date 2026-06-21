"""Artış potansiyeli tespiti."""

from hibrit_trader.growth_potential import (
    build_growth_watchlist,
    classify_growth_stage,
    compute_growth_potential,
)
from hibrit_trader.scanner import Pair


def _pair(**kw) -> Pair:
    defaults = dict(
        chain="solana",
        dex="gecko",
        name="TEST / SOL",
        token_address="t1",
        pool_address="p1",
        price_usd=1.0,
        liquidity_usd=100_000,
        vol_h24=1e6,
        vol_h1=100_000,
        vol_m5=20_000,
        chg_h1=10.0,
        chg_m5=2.0,
        chg_h24=15.0,
        txns_h1=200,
    )
    defaults.update(kw)
    return Pair(**defaults)


def test_classify_erken_ivme():
    assert classify_growth_stage(_pair(chg_h1=8, chg_m5=1.2, vol_m5=25_000)) == "erken"
    assert classify_growth_stage(_pair(chg_h1=18, chg_m5=2, vol_m5=30_000)) == "ivme"
    assert classify_growth_stage(_pair(chg_h1=50)) == "gec_pump"


def test_cex_erken_when_dex_flat():
    assert classify_growth_stage(_pair(chg_h1=-1, chg_m5=0), cex_hold=60) == "cex_erken"


def test_upside_ranks_erken_higher():
    early = compute_growth_potential(62, _pair(chg_h1=9, chg_m5=1.5, vol_m5=28_000), cex_hold=58)
    late = compute_growth_potential(70, _pair(chg_h1=48, chg_m5=5, vol_m5=40_000), cex_hold=40)
    assert early["upside_score"] > late["upside_score"]
    assert early["stage"] == "erken"
    assert late["stage"] == "gec_pump"


def test_classify_gec_pump_on_h24_chaton():
    """h1 düşmüş olsa bile h24 +2000% = geç pump (DexScreener trending sınıfı)."""
    import time as _time

    chaton = _pair(
        chg_h1=-11.0,
        chg_h24=2268.0,
        chg_m5=-2.0,
        pool_created_at=_time.time() - 3600 * 23,
    )
    assert classify_growth_stage(chaton) == "gec_pump"


def test_build_growth_watchlist_merges_cex():
    ranked = [(60.0, _pair(name="HOT / SOL"))]
    rows = build_growth_watchlist(
        ranked,
        cex_scores={"HOT": 55},
        whale_signals=[],
        binance_holds=[{"symbol": "TON", "score": 72, "reason": "CEX tut 72"}],
        okx_holds=[],
        limit=10,
    )
    symbols = {r["symbol"] for r in rows}
    assert "HOT" in symbols
    assert "TON" in symbols
    ton = next(r for r in rows if r["symbol"] == "TON")
    assert ton["stage"] == "cex_erken"
    assert ton["source"] == "cex"
