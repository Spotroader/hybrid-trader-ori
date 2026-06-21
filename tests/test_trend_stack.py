import pandas as pd

from hibrit_trader.advanced_scan.indicators import (
    chandelier_long_stop,
    halftrend_bull,
    market_structure_bull,
    supertrend,
    ut_bot_alerts,
)
from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
from hibrit_trader.scanner import Pair
from hibrit_trader.trend_stack import compute_trend_stack, dex_trend_metrics, trend_stack_for_symbol


def _uptrend_df(n: int = 80) -> tuple[pd.Series, pd.Series, pd.Series]:
    closes = pd.Series([100 + i * 0.8 + (i % 3) * 0.1 for i in range(n)], dtype=float)
    highs = closes + 0.5
    lows = closes - 0.5
    return highs, lows, closes


def test_supertrend_uptrend():
    h, l, c = _uptrend_df()
    st = supertrend(h, l, c)
    assert st["in_uptrend"] is True
    assert st["direction"] == 1


def test_supertrend_entry_stack():
    m = {
        "above_ema200": True,
        "supertrend_bull": True,
        "supertrend_buy": False,
        "supertrend_whipsaw": False,
        "halftrend_bull": True,
        "msb_bull": True,
        "vol_spike": 1.4,
        "macd_hist": 0.001,
        "chg_24h_pct": 5.0,
    }
    r = compute_trend_stack(m)
    assert r.entry_ok
    assert r.supertrend
    assert r.primary == "supertrend"


def test_supertrend_blocks_whipsaw():
    m = {
        "above_ema200": True,
        "supertrend_bull": True,
        "supertrend_whipsaw": True,
        "halftrend_bull": True,
        "msb_bull": True,
        "vol_spike": 1.5,
    }
    r = compute_trend_stack(m)
    assert not r.entry_ok
    assert "whipsaw" in r.reason.lower() or "testere" in r.reason.lower()


def test_halftrend_and_msb_on_series():
    h, l, c = _uptrend_df()
    assert halftrend_bull(h, l, c) is True
    assert market_structure_bull(h, l, c) is True


def test_ut_bot_alert_entry_path():
    m = {
        "above_ema200": True,
        "supertrend_bull": True,
        "supertrend_buy": True,
        "supertrend_whipsaw": False,
        "halftrend_bull": False,
        "msb_bull": True,
        "vol_spike": 1.5,
        "ut_bot_alert": True,
        "ut_bot_bull": True,
    }
    r = compute_trend_stack(m)
    assert r.entry_ok
    assert r.ut_bot
    assert "UT" in r.reason


def test_dex_fallback_when_no_cex():
    pair = Pair(
        chain="solana",
        dex="raydium",
        pool_address="P",
        token_address="T",
        name="MEME / SOL",
        price_usd=0.01,
        liquidity_usd=150_000,
        vol_m5=25_000,
        vol_h1=80_000,
        vol_h24=500_000,
        chg_m5=2.5,
        chg_h1=5.0,
        chg_h24=12.0,
        txns_h1=200,
    )
    r = trend_stack_for_symbol("MEME", {}, pair)
    assert r.dex_fallback
    assert r.entry_ok


def test_ut_bot_and_chandelier_indicators():
    h, l, c = _uptrend_df()
    ut = ut_bot_alerts(h, l, c)
    assert "bull" in ut
    ce = chandelier_long_stop(h, l, c)
    assert ce > 0


def test_chandelier_runner_exit():
    import time

    pos = Position(
        pair_name="X",
        chain="solana",
        token_address="T",
        pool_address="P",
        entry_price=80.0,
        amount_token=1.0,
        cost_usd=80.0,
        opened_at="2026-01-01T00:00:00Z",
        entry_score=70.0,
        peak_price_usd=130.0,
        trail_armed=True,
        runner_mode=True,
        atr_pct_at_entry=10.0,
        opened_ts=time.time(),
    )
    # chandelier stop ~130 * (1 - 0.30) = 91; price 90 still +12.5% vs entry
    d = evaluate_exit_ladder(pos, 90.0, 50.0, 0, ExitPolicy(), None)
    assert d is not None
    assert d.kind == "exit_full"
    assert "chandelier" in d.reason
