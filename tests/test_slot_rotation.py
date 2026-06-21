"""Slot rotation — zayıf pozisyonu bırak, güçlü adaya geç."""

from hibrit_trader.paper import PaperBroker, Position
from hibrit_trader.scanner import Pair
from hibrit_trader.slot_rotation import (
    candidate_strength,
    hold_quality_score,
    pick_weakest_hold,
    should_rotate,
)


def _pos(**kw) -> Position:
    base = dict(
        pair_name="WEAK / SOL",
        chain="solana",
        token_address="T1",
        pool_address="P1",
        entry_price=1.0,
        amount_token=100.0,
        cost_usd=20.0,
        opened_at="2026-01-01T00:00:00+00:00",
        entry_score=40.0,
    )
    base.update(kw)
    return Position(**base)


def test_pick_weakest_by_hold_quality():
    weak = _pos(pool_address="P1", entry_score=35.0)
    strong = _pos(pool_address="P2", pair_name="STRONG / SOL", entry_score=70.0)
    picked = pick_weakest_hold(
        [weak, strong],
        dex_scores={"P1": 30.0, "P2": 65.0},
        last_prices={"P1": 0.95, "P2": 1.10},
    )
    assert picked is not None
    victim, score = picked
    assert victim.pool_address == "P1"
    assert score < hold_quality_score(strong, dex_score=65.0, unrealized_pnl_pct=10.0)


def test_should_rotate_requires_gap_and_confluence(monkeypatch):
    monkeypatch.setenv("ROTATION_MIN_SCORE_GAP", "12")
    monkeypatch.setenv("ROTATION_MIN_CONFLUENCE", "55")
    ok, _ = should_rotate(weakest_hold_score=50.0, conf_score=60.0, dex_score=70.0)
    assert ok
    ok, msg = should_rotate(weakest_hold_score=58.0, conf_score=60.0, dex_score=70.0)
    assert not ok
    assert "yetersiz" in msg
    ok, msg = should_rotate(weakest_hold_score=40.0, conf_score=50.0, dex_score=70.0)
    assert not ok
    assert "konfluans" in msg


def test_candidate_strength_blend():
    s = candidate_strength(60.0, 80.0)
    assert 60 < s < 80
