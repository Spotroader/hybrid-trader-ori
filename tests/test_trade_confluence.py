"""Birleşik konfluans skoru — DEX + CEX + balina + Saito."""

from hibrit_trader.scanner import Pair
from hibrit_trader.trade_confluence import (
    ConfluenceSnapshot,
    build_confluence_snapshot,
    compute_trade_confluence,
)


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana", dex="raydium", pool_address="P1", token_address="T1",
        name="HOT / SOL", price_usd=1.0, liquidity_usd=200_000,
        vol_m5=20_000, vol_h1=100_000, vol_h24=800_000,
        chg_m5=3.0, chg_h1=12.0, chg_h24=25.0, txns_h1=400,
    )
    base.update(kw)
    return Pair(**base)


def test_genesis_bypasses_supertrend_confluence():
    """Genesis aday — Supertrend yokken bile paper agresif giriş."""
    import time

    snap = ConfluenceSnapshot(
        cex_scores={},
        whale_by_symbol={},
        confluence_min=45.0,
        min_layers=1,
        aggressive=True,
    )
    young = _pair(
        chg_m5=5.0,
        chg_h1=12.0,
        chg_h24=15.0,
        vol_m5=15_000,
        txns_m5=20,
        pool_created_at=time.time() - 3600,
        liquidity_usd=25_000,
    )
    r = compute_trade_confluence(
        62.0,
        young,
        snap,
        entry_min=50.0,
        smart_money_ok=False,
        genesis_ok=True,
    )
    assert r.enter_ok, r.blocker
    assert "GEN" in r.layer_labels


def test_confluence_requires_two_layers():
    snap = ConfluenceSnapshot(
        cex_scores={},
        whale_by_symbol={},
        confluence_min=58.0,
        min_layers=2,
    )
    weak = _pair(chg_m5=0.1, chg_h1=0.2, chg_h24=-15.0, vol_m5=500, vol_h1=100_000)
    r = compute_trade_confluence(
        70.0, weak, snap, entry_min=55.0, smart_money_ok=False
    )
    assert not r.enter_ok
    assert "katman" in (r.blocker or "") or "Supertrend" in (r.blocker or "")


def test_confluence_merged_score_high_when_aligned():
    metrics = {
        "above_ema200": True,
        "supertrend_bull": True,
        "supertrend_whipsaw": False,
        "halftrend_bull": True,
        "msb_bull": True,
        "vol_spike": 1.5,
    }
    snap = build_confluence_snapshot(
        binance_holds=[{"symbol": "HOT", "score": 70, "metrics": metrics}],
        okx_holds=[],
        whale_signals=[
            {
                "symbol": "HOT",
                "buy_signal": True,
                "score": 80,
                "wallet_count": 4,
            }
        ],
        brain_verdict=None,
        macro_avg=52.0,
        brain_penalty=0.0,
        confluence_min=58.0,
        min_layers=2,
    )
    r = compute_trade_confluence(
        72.0, _pair(), snap, entry_min=55.0, smart_money_ok=True
    )
    assert r.layer_count >= 2
    assert r.score >= 58.0
    assert r.enter_ok


def test_confluence_brain_tam_boosts():
    snap = build_confluence_snapshot(
        binance_holds=[{"symbol": "HOT", "score": 60}],
        okx_holds=[],
        whale_signals=[],
        brain_verdict=type("V", (), {"tam_isabet_symbols": ["HOT"], "top_picks": [], "regime": "neutral"})(),
        macro_avg=50.0,
        brain_penalty=0.0,
        min_layers=2,
    )
    r = compute_trade_confluence(
        65.0, _pair(), snap, entry_min=55.0, smart_money_ok=True
    )
    assert r.layers.get("brain") is True
    assert "BRAIN" in r.layer_labels
