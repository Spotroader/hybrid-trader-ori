from hibrit_trader.decision import DecisionPolicy, evaluate_entry, evaluate_exit, has_profit_edge
from hibrit_trader.exit_policy import ExitPolicy, evaluate_exit_ladder
from hibrit_trader.paper import Position
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


def test_profit_edge_blocks_weak_momentum():
    policy = DecisionPolicy()
    weak = _pair(chg_h1=0.5, chg_m5=0.2, vol_m5=500, vol_h1=50_000)
    ok, _ = has_profit_edge(weak, 20.0, policy)
    assert not ok


def test_profit_edge_includes_quote_slippage():
    policy = DecisionPolicy(min_edge_after_cost_pct=4.0)
    pair = _pair()
    ok, _ = has_profit_edge(pair, 20.0, policy, quote_slippage_pct=15.0)
    assert not ok


def test_entry_requires_score_and_edge():
    policy = DecisionPolicy(require_smart_money=False)
    pair = _pair()
    d = evaluate_entry(
        70.0, pair, 20.0, policy,
        safety_ok=True, kill_switch=False, open_count=0,
        daily_pnl=0.0, daily_loss_limit=30.0, already_held=False, live_allowed=True,
    )
    assert d.action == "enter"

    low = evaluate_entry(
        50.0, pair, 20.0, policy,
        safety_ok=True, kill_switch=False, open_count=0,
        daily_pnl=0.0, daily_loss_limit=30.0, already_held=False, live_allowed=True,
    )
    assert low.action == "skip"


def test_late_pump_skipped():
    policy = DecisionPolicy(require_smart_money=False)
    late = _pair(chg_h1=55.0, chg_m5=2.0)
    d = evaluate_entry(
        70.0, late, 20.0, policy,
        safety_ok=True, kill_switch=False, open_count=0,
        daily_pnl=0.0, daily_loss_limit=30.0, already_held=False, live_allowed=True,
    )
    assert d.action == "skip"
    assert "geç kalındı" in d.reason


def test_macro_raises_entry_threshold():
    policy = DecisionPolicy(entry_score_min=65.0, macro_entry_penalty=10.0, require_smart_money=False)
    pair = _pair()
    d = evaluate_entry(
        68.0, pair, 20.0, policy,
        safety_ok=True, kill_switch=False, open_count=0,
        daily_pnl=0.0, daily_loss_limit=30.0, already_held=False, live_allowed=True,
        macro_avg=30.0,
    )
    assert d.action == "skip"
    assert "makro" in d.reason


def test_exit_tp1_partial():
    policy = DecisionPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
        peak_price_usd=1.0, initial_amount_token=20.0,
    )
    # +20% runner arms trail — satış yok
    ex = evaluate_exit(pos, 1.20, 80.0, 0, policy)
    assert ex is None
    assert pos.trail_armed
    assert pos.runner_mode
    # +45% tp1 kısmi
    ex = evaluate_exit(pos, 1.46, 80.0, 0, policy)
    assert ex is not None
    assert ex.action == "exit_partial"
    assert ex.sell_fraction == 0.25
    assert "tp1" in ex.reason


def test_exit_runner_trail_from_peak():
    policy = DecisionPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
        peak_price_usd=1.35, initial_amount_token=20.0,
        trail_armed=True, runner_mode=True, tp1_done=True,
    )
    ex = evaluate_exit(pos, 1.18, 80.0, 0, policy)
    assert ex is not None
    assert ex.action == "exit"
    assert "trail" in ex.reason


def test_exit_scratch():
    policy = DecisionPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
    )
    ex = evaluate_exit(pos, 0.97, 80.0, 0, policy)
    assert ex is not None
    assert "scratch" in ex.reason


def test_exit_score_still_full():
    policy = DecisionPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
    )
    # +3% kâr yok sayılır (<5%) — düşük skorda çık
    ex = evaluate_exit(pos, 1.03, 40.0, 0, policy)
    assert ex is not None
    assert ex.action == "exit"
    assert ex.reason == "fırsat bitti"


def test_exit_profit_holds_on_low_score():
    policy = DecisionPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
        peak_price_usd=1.12,
    )
    # +10% kâr — skor düşse bile TP/trail beklesin
    ex = evaluate_exit(pos, 1.10, 40.0, 0, policy)
    assert ex is None


def test_breakeven_stop():
    ep = ExitPolicy()
    pos = Position(
        pair_name="X", chain="solana", token_address="T", pool_address="P",
        entry_price=1.0, amount_token=20.0, cost_usd=20.0, opened_at="t", entry_score=70.0,
        breakeven_armed=True, peak_price_usd=1.1,
    )
    ex = evaluate_exit_ladder(pos, 1.004, 80.0, 0, ep)
    assert ex is not None
    assert ex.reason == "break-even stop"
