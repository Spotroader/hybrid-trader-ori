"""Dexscreener trending stratejisi."""

from hibrit_trader.dex_trending_strategy import evaluate_trending, trending_score
from hibrit_trader.scanner import Pair
from hibrit_trader.trade_confluence import ConfluenceSnapshot, compute_trade_confluence


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana",
        dex="raydium",
        pool_address="P1",
        token_address="T1",
        name="HAPPY / SOL",
        price_usd=0.001,
        liquidity_usd=79_000,
        vol_m5=400_000,
        vol_h1=2_000_000,
        vol_h24=5_600_000,
        chg_m5=2.5,
        chg_h1=45.0,
        chg_h24=2800.0,
        txns_h1=5000,
        txns_h24=120_000,
        boost_score=530,
    )
    base.update(kw)
    return Pair(**base)


def test_trending_score_hot_pair():
    s = trending_score(_pair())
    assert s >= 55


def test_trending_rejects_dump():
    sig = evaluate_trending(_pair(chg_m5=-15.0))
    assert not sig.entry_ok
    assert sig.dump_risk


def test_trending_entry_ok_on_boost():
    sig = evaluate_trending(_pair())
    assert sig.entry_ok
    assert sig.score >= 42


def test_confluence_ds_fast_path(monkeypatch):
    monkeypatch.setenv("DEX_TRENDING_FAST", "1")
    snap = ConfluenceSnapshot(
        cex_scores={},
        whale_by_symbol={},
        confluence_min=45.0,
        min_layers=2,
        aggressive=True,
    )
    weak_trend = _pair(chg_m5=0.1, chg_h1=0.2, chg_h24=-15.0, vol_m5=500, boost_score=0)
    r = compute_trade_confluence(60.0, weak_trend, snap, entry_min=50.0, smart_money_ok=False)
    assert not r.enter_ok

    hot = _pair()
    r2 = compute_trade_confluence(55.0, hot, snap, entry_min=50.0, smart_money_ok=False)
    assert r2.layers.get("trend") is True
    assert "DS" in r2.layer_labels
    assert r2.enter_ok
