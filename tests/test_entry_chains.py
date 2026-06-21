"""ENTRY_CHAINS — EVM giriş kapalı, yalnız Sol slot."""

from hibrit_trader.config import Settings
from hibrit_trader.paper import PaperBroker
from hibrit_trader.safety import SafetyReport
from hibrit_trader.scanner import Pair
from hibrit_trader.session import Engine


def _pair(**kw) -> Pair:
    temel = dict(
        chain="solana",
        dex="raydium",
        pool_address="P1",
        token_address="T1",
        name="HOT / SOL",
        price_usd=1.0,
        liquidity_usd=200_000,
        vol_m5=20_000,
        vol_h1=100_000,
        vol_h24=800_000,
        chg_m5=3.0,
        chg_h1=12.0,
        chg_h24=25.0,
        txns_h1=300,
        boost_score=100,
    )
    temel.update(kw)
    return Pair(**temel)


def test_evm_entry_blocked_sol_only(tmp_path, monkeypatch):
    sol = _pair()
    evm = _pair(
        chain="arbitrum",
        dex="uniswap",
        pool_address="P2",
        token_address="T2",
        name="CHIP / USDC",
    )
    settings = Settings(
        entry_chains=("solana",),
        scan_chains=("solana", "arbitrum"),
        max_position_usd=20.0,
        confluence_min=45.0,
        confluence_min_layers=1,
        confluence_required=False,
        entry_score_min=50.0,
    )
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=1000.0,
    )
    engine = Engine(settings, broker)
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [evm, sol])
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=True),
    )
    monkeypatch.setattr(engine, "_sync_market_intel", lambda pairs, **k: None)
    monkeypatch.setattr(
        "hibrit_trader.session.rank",
        lambda pairs, mp, cex_scores=None, client=None: [(70.0, evm), (60.0, sol)],
    )
    engine._binance_holds = [{"symbol": "HOT", "score": 68, "metrics": {}}]
    engine._whale_signals = [
        {"symbol": "HOT", "pair": "HOT / SOL", "chain": "solana", "buy_signal": True, "score": 75}
    ]
    engine._holds_updated_at = 1.0
    engine.tick()
    assert len(broker.positions) == 1
    assert broker.positions[0].chain == "solana"
