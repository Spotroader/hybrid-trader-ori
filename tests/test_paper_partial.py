from hibrit_trader.paper import PaperBroker, Position
from hibrit_trader.scanner import Pair


def _pair() -> Pair:
    return Pair(
        chain="solana", dex="raydium", pool_address="P1", token_address="T1",
        name="HOT / SOL", price_usd=1.0, liquidity_usd=200_000,
        vol_m5=20_000, vol_h1=100_000, vol_h24=800_000,
        chg_m5=3.0, chg_h1=12.0, chg_h24=25.0, txns_h1=300,
    )


def test_sell_partial_keeps_position(tmp_path):
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=100.0,
    )
    pos = broker.buy(_pair(), 20.0, 70.0)
    initial = pos.initial_amount_token
    trade = broker.sell_partial(pos, 0.30, 1.25, 200_000, "tp1")
    assert trade.pnl_usd != 0
    assert len(broker.positions) == 1
    remaining = broker.positions[0]
    assert remaining.amount_token < initial
    assert remaining.cost_usd < 20.0
