from unittest.mock import patch

from hibrit_trader.brain.adversary import predict_counterparty
from hibrit_trader.brain.orchestrator import run_brain


def test_adversary_trap_on_high_fear_greed():
    report = predict_counterparty(
        macro_avg=50,
        fear_greed=85,
        top_scan=[{"symbol": "BTC", "deriv_score": 30, "reason": "long kalabalık"}],
    )
    assert report.dominant_trap or any(m.impact == "trap" for m in report.moves)


@patch("hibrit_trader.brain.orchestrator.fetch_fear_greed")
@patch("hibrit_trader.brain.orchestrator.run_advanced_scan")
def test_run_brain_defensive_on_trap(mock_scan, mock_fg):
    mock_fg.return_value = {"value": 82, "label": "Extreme Greed", "source": "test"}
    mock_scan.return_value = {
        "results": [
            {
                "symbol": "BTC",
                "score": 70,
                "deriv_score": 28,
                "reason": "long kalabalık",
                "tam_isabet": False,
            },
            {"symbol": "ETH", "score": 45, "deriv_score": 25, "reason": "funding", "tam_isabet": False},
        ],
    }
    v = run_brain(limit=5)
    assert v.regime in ("risk_off", "neutral", "risk_on")
    assert v.action_bias in ("defensive", "neutral", "aggressive")
    assert v.entry_penalty >= 0
    assert v.counterparty_thesis
