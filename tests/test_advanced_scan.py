"""Gelişmiş tarama modül testleri."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from hibrit_trader.advanced_scan.indicators import rsi
from hibrit_trader.advanced_scan.runner import list_modes, run_advanced_scan
from hibrit_trader.advanced_scan.social import social_status


def test_social_red():
    s = social_status()
    assert s["enabled"] is False
    assert s["status"] == "red"


def test_list_modes_has_six():
    modes = list_modes()
    assert len(modes) == 6
    ids = {m["id"] for m in modes}
    assert "cex" in ids and "social" in ids


def test_rsi_flat():
    closes = pd.Series([100.0] * 30)
    assert 45 <= rsi(closes) <= 55


@patch("hibrit_trader.advanced_scan.runner.scan_cex")
@patch("hibrit_trader.advanced_scan.runner.scan_news")
@patch("hibrit_trader.advanced_scan.runner.scan_whale_proxy")
@patch("hibrit_trader.advanced_scan.runner.scan_derivatives")
def test_run_advanced_scan_merge(mock_deriv, mock_whale, mock_news, mock_cex):
    mock_cex.return_value = [
        {"symbol": "SOL", "exchange": "binance", "score": 70.0, "reason": "teknik", "metrics": {}},
    ]
    mock_news.return_value = {"SOL": {"score": 75.0, "headline": "Solana rally", "sentiment": "bullish"}}
    mock_whale.return_value = {"SOL": {"score": 60.0, "reason": "whale proxy"}}
    mock_deriv.return_value = {"SOL": {"score": 55.0, "reason": "funding ok", "funding_rate": 0.01, "oi_change_pct": 2}}

    out = run_advanced_scan(["cex", "news", "whale", "derivatives"], limit=5)
    assert out["count"] >= 1
    assert out["results"][0]["symbol"] == "SOL"
    assert out["results"][0]["tam_isabet"] is True
