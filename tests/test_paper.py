from hibrit_trader.paper import PaperBroker
from hibrit_trader.scanner import Pair


def _pair(**kw) -> Pair:
    temel = dict(
        chain="solana", dex="raydium", pool_address="P1", token_address="T1",
        name="TEST / SOL", price_usd=1.0, liquidity_usd=100_000,
        vol_m5=5000, vol_h1=50_000, vol_h24=600_000,
        chg_m5=1.0, chg_h1=8.0, chg_h24=15.0, txns_h1=150,
    )
    temel.update(kw)
    return Pair(**temel)


def test_buy_sell_pnl(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=1000.0,
    )
    pair = _pair(price_usd=10.0, liquidity_usd=500_000)
    pos = broker.buy(pair, 100.0, 70.0)
    assert broker.balance < 900  # gas düşüldü
    trade = broker.sell(pos, current_price=12.0, liquidity_usd=500_000, reason="hedef")
    assert trade.pnl_usd > 0
    assert len(broker.positions) == 0


def test_buy_yetersiz_bakiye(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=10.0,
    )
    try:
        broker.buy(_pair(), 100.0, 70.0)
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_state_kalici(tmp_path):
    path = str(tmp_path / "state.json")
    trades = str(tmp_path / "trades.jsonl")
    b1 = PaperBroker(state_path=path, trades_path=trades, start_balance_usd=500.0)
    b1.buy(_pair(pool_address="PX"), 50.0, 65.0)
    b2 = PaperBroker(state_path=path, trades_path=trades, start_balance_usd=500.0)
    assert len(b2.positions) == 1
    assert b2.balance < 450


def test_gas_dusumu(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=1000.0,
    )
    before = broker.balance
    broker.buy(_pair(chain="bsc"), 20.0, 70.0)  # bsc gas = 0.15
    assert broker.balance == before - 20.0 - 0.15


def test_summary(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=100.0,
    )
    s = broker.summary()
    assert "balance" in s and "win_rate" in s
    assert s["start_balance_usd"] == 100.0
    assert s["session_pnl"] == 0.0


def test_summary_session_pnl_after_round_trip(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=100.0,
    )
    pair = _pair(chain="bsc", price_usd=10.0, liquidity_usd=500_000)
    pos = broker.buy(pair, 15.0, 70.0)
    broker.sell(pos, current_price=12.0, liquidity_usd=500_000, reason="hedef")
    s = broker.summary()
    assert s["trade_count"] == 1
    assert s["wins"] == 1
    assert s["gross_profit"] > 0
    assert s["session_pnl"] == round(broker.balance - 100.0, 2)
    assert s["gas_paid_est"] > 0
