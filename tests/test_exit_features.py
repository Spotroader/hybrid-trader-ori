from hibrit_trader.position_sizer import compute_position_usd
from hibrit_trader.config import Settings
from hibrit_trader.paper import PaperBroker, Trade
from hibrit_trader.scanner import Pair


def _pair(**kw) -> Pair:
    base = dict(
        chain="solana", dex="raydium", pool_address="P1", token_address="T1",
        name="HOT / SOL", price_usd=1.0, liquidity_usd=200_000,
        vol_m5=20_000, vol_h1=100_000, vol_h24=800_000,
        chg_m5=3.0, chg_h1=12.0, chg_h24=25.0, txns_h1=300,
    )
    base.update(kw)
    return Pair(**base)


def test_position_size_scales_with_streak(tmp_path):
    settings = Settings(max_position_usd=20.0)
    broker = PaperBroker(
        state_path=str(tmp_path / "s.json"),
        trades_path=str(tmp_path / "t.jsonl"),
    )
    broker.trades = [
        Trade("a", "solana", 1, 1, 10, 12, 2, "t", "t", "w"),
        Trade("b", "solana", 1, 1, 10, 12, 2, "t", "t", "w"),
        Trade("c", "solana", 1, 1, 10, 12, 2, "t", "t", "w"),
    ]
    size = compute_position_usd(settings, broker, _pair())
    assert size > 20.0


def test_smart_money_blocks_low_txns():
    from hibrit_trader.smart_money import smart_money_entry_ok

    ok, _ = smart_money_entry_ok(
        _pair(txns_h1=10, chg_h1=1.0, chg_m5=0.2, vol_h1=10_000, liquidity_usd=20_000),
        min_wallets=3,
    )
    assert not ok


def test_smart_money_ok_high_activity():
    from hibrit_trader.smart_money import smart_money_entry_ok

    ok, note = smart_money_entry_ok(_pair(txns_h1=400, chg_h1=8, vol_h1=200_000), min_wallets=3)
    assert ok
    assert "alpha" in note
