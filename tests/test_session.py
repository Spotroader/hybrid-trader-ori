from hibrit_trader.config import Settings
from hibrit_trader.paper import PaperBroker
from hibrit_trader.safety import SafetyReport
from hibrit_trader.scanner import Pair
from hibrit_trader.session import Engine


def _pair(**kw) -> Pair:
    temel = dict(
        chain="solana", dex="raydium", pool_address="P1", token_address="T1",
        name="HOT / SOL", price_usd=1.0, liquidity_usd=200_000,
        vol_m5=20_000, vol_h1=100_000, vol_h24=800_000,
        chg_m5=3.0, chg_h1=12.0, chg_h24=25.0, txns_h1=300,
    )
    temel.update(kw)
    return Pair(**temel)


def _engine(tmp_path, balance=1000.0, daily_loss=30.0):
    settings = Settings(
        max_position_usd=20.0,
        daily_loss_limit_usd=daily_loss,
        confluence_min=58.0,
        confluence_min_layers=2,
    )
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
        start_balance_usd=balance,
    )
    return Engine(settings, broker), broker


def _supertrend_metrics() -> dict:
    return {
        "above_ema200": True,
        "supertrend_bull": True,
        "supertrend_buy": False,
        "supertrend_whipsaw": False,
        "halftrend_bull": True,
        "msb_bull": True,
        "vol_spike": 1.4,
        "macd_hist": 0.002,
        "chg_24h_pct": 6.0,
        "rsi": 48.0,
    }


def _seed_confluence(engine) -> None:
    """CEX+balina+Supertrend katmanları — HOT / SOL ile hizalı."""
    metrics = _supertrend_metrics()
    engine._binance_holds = [{"symbol": "HOT", "score": 68, "metrics": metrics}]
    engine._okx_holds = []
    engine._whale_signals = [
        {
            "symbol": "HOT",
            "pair": "HOT / SOL",
            "chain": "solana",
            "buy_signal": True,
            "score": 75,
            "wallet_count": 4,
        }
    ]
    engine._holds_updated_at = 1.0


def test_yuksek_skor_temiz_giris(tmp_path, monkeypatch):
    hot = _pair()
    engine, broker = _engine(tmp_path)
    _seed_confluence(engine)
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [hot])
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=True),
    )
    monkeypatch.setattr(engine, "_sync_market_intel", lambda pairs: None)
    engine.tick()
    assert len(broker.positions) == 1


def test_red_cift_girmez(tmp_path, monkeypatch):
    hot = _pair()
    engine, broker = _engine(tmp_path)
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [hot])
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=False, reasons=["honeypot"]),
    )
    engine.tick()
    assert len(broker.positions) == 0


def test_tp_kapanir(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_AGGRESSIVE", "0")
    settings = Settings(
        max_position_usd=20.0,
        daily_loss_limit_usd=30.0,
        paper_aggressive=False,
    )
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
    )
    engine = Engine(settings, broker)
    hot = _pair(price_usd=1.0)
    pos = broker.buy(hot, 20.0, 70.0)
    # +45% fiyat → TP1 kademeli (%25 sat) — +20% sadece runner trail
    risen = _pair(price_usd=1.47)
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [risen])
    engine._last_prices[pos.pool_address] = 1.47
    engine.tick()
    assert len(broker.positions) == 1
    assert len(broker.trades) == 1
    assert broker.trades[-1].exit_reason.startswith("tp1")
    remaining = broker.positions[0]
    assert remaining.tp1_done


def test_dusuk_skor_cikis(tmp_path, monkeypatch):
    hot = _pair(price_usd=1.0)
    engine, broker = _engine(tmp_path)
    pos = broker.buy(hot, 20.0, 70.0)
    cold = _pair(price_usd=1.0, vol_m5=100, vol_h1=500, chg_h1=0.1)
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [cold])
    monkeypatch.setattr(
        "hibrit_trader.session.rank",
        lambda pairs, mp, cex_scores=None, client=None: [(30.0, cold)],
    )
    engine._last_prices[pos.pool_address] = 1.0
    engine.tick()
    assert len(broker.positions) == 0
    assert broker.trades[-1].exit_reason == "fırsat bitti"


def test_gunluk_zarar_limiti(tmp_path, monkeypatch):
    hot = _pair()
    engine, broker = _engine(tmp_path, daily_loss=5.0)
    # Önce zararlı işlem simüle et
    engine._daily_pnl = -10.0
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [hot])
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=True),
    )
    engine.tick()
    assert len(broker.positions) == 0  # günlük limit aşıldı, giriş yok


def test_slot_rotation_weakest_out(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOT_ROTATION", "1")
    monkeypatch.setenv("ROTATION_MIN_SCORE_GAP", "5")
    monkeypatch.setenv("ROTATION_MIN_CONFLUENCE", "50")

    settings = Settings(
        max_position_usd=20.0,
        daily_loss_limit_usd=30.0,
        max_open_positions=2,
        confluence_min=58.0,
        confluence_min_layers=2,
    )
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
    )
    engine = Engine(settings, broker)

    weak1 = _pair(pool_address="W1", token_address="TW1", name="WEAK1 / SOL")
    weak2 = _pair(pool_address="W2", token_address="TW2", name="WEAK2 / SOL")
    hot = _pair(pool_address="H1", token_address="TH1", name="HOT / SOL", boost_score=500)
    broker.buy(weak1, 20.0, 40.0)
    broker.buy(weak2, 20.0, 42.0)
    _seed_confluence(engine)

    all_pairs = [hot, weak1, weak2]
    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: all_pairs)
    monkeypatch.setattr(
        "hibrit_trader.session.rank",
        lambda pairs, mp, cex_scores=None, client=None: [
            (75.0, hot),
            (50.0, weak1),
            (52.0, weak2),
        ],
    )
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=True),
    )
    monkeypatch.setattr(engine, "_sync_market_intel", lambda pairs: None)

    engine.tick()

    names = {p.pair_name for p in broker.positions}
    assert "HOT / SOL" in names
    assert "WEAK1 / SOL" not in names
    assert len(broker.positions) == 2
    assert any("slot rotate" in t.exit_reason for t in broker.trades)


def test_slot_rotation_kapali_giris_yok(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOT_ROTATION", "0")

    settings = Settings(
        max_position_usd=20.0,
        max_open_positions=1,
        confluence_min=40.0,
        confluence_min_layers=1,
    )
    broker = PaperBroker(
        state_path=str(tmp_path / "state.json"),
        trades_path=str(tmp_path / "trades.jsonl"),
    )
    engine = Engine(settings, broker)
    held = _pair(pool_address="W1", token_address="TW1", name="HELD / SOL")
    hot = _pair(pool_address="H1", token_address="TH1", name="HOT / SOL")
    broker.buy(held, 20.0, 50.0)

    monkeypatch.setattr("hibrit_trader.session.scan_all", lambda *a, **k: [hot, held])
    monkeypatch.setattr(
        "hibrit_trader.session.rank",
        lambda pairs, mp, cex_scores=None, client=None: [(80.0, hot), (50.0, held)],
    )
    monkeypatch.setattr(
        "hibrit_trader.session.check_token",
        lambda *a, **k: SafetyReport(ok=True),
    )
    monkeypatch.setattr(engine, "_sync_market_intel", lambda pairs: None)

    engine.tick()
    assert len(broker.positions) == 1
    assert broker.positions[0].pair_name == "HELD / SOL"
