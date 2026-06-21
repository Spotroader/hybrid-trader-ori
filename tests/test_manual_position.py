"""Manuel pozisyon kapatma."""


from hibrit_trader.config import Settings
from hibrit_trader.paper import PaperBroker
from hibrit_trader.scanner import Pair
from hibrit_trader.session import Engine


def _pair() -> Pair:
    return Pair(
        chain="solana",
        dex="raydium",
        name="TEST / SOL",
        token_address="T1",
        pool_address="P1",
        price_usd=1.0,
        liquidity_usd=200_000,
        vol_m5=10_000,
        vol_h1=50_000,
        vol_h24=200_000,
        chg_h1=5.0,
        chg_m5=1.0,
        chg_h24=10.0,
        txns_h1=500,
    )


def test_manual_close_position(tmp_path):
    settings = Settings(max_open_positions=5, paper_start_balance_usd=100)
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=100,
    )
    engine = Engine(settings, broker)
    pos = broker.buy(_pair(), 20.0, 70.0)
    engine._last_prices[pos.pool_address] = 1.1
    out = engine.manual_close_position(pos.pool_address, fraction=1.0)
    assert out["ok"] is True
    assert len(broker.positions) == 0
    assert len(broker.trades) == 1
