"""Faz 8b — RugCheck, havuz filtresi, Helius alpha, güvenlik birleşimi."""

import time
from unittest.mock import MagicMock

import httpx

from hibrit_trader.rugcheck import summary_from_payload
from hibrit_trader.safety import SafetyReport, _merge_solana_safety
from hibrit_trader.scanner import Pair, parse_pool
from hibrit_trader.smart_money import estimate_wallet_buyers
from hibrit_trader.token_filters import pool_age_hours, token_filter_ok
from tests.test_faz8 import _pair
from tests.test_scanner import ORNEK_HAVUZ


def test_parse_pool_created_at():
    item = dict(ORNEK_HAVUZ)
    item["attributes"] = dict(item["attributes"])
    item["attributes"]["pool_created_at"] = "2026-06-11T10:00:00Z"
    p = parse_pool("solana", item)
    assert p is not None
    assert p.pool_created_at is not None
    assert pool_age_hours(p) is not None


def test_token_filter_rejects_young_pool(monkeypatch):
    monkeypatch.setenv("MIN_POOL_AGE_HOURS", "24")
    created = time.time() - 3600
    pair = _pair(pool_created_at=created, liquidity_usd=50_000)
    ok, note = token_filter_ok(pair)
    assert not ok
    assert "yeni" in note


def test_token_filter_genesis_bypasses_min_age(monkeypatch):
    monkeypatch.setenv("MIN_POOL_AGE_HOURS", "24")
    pair = _pair(pool_created_at=time.time() - 600, liquidity_usd=50_000)
    ok, note = token_filter_ok(pair, genesis_ok=True)
    assert ok
    assert "genesis" in note


def test_token_filter_rejects_low_liquidity(monkeypatch):
    monkeypatch.setenv("MIN_POOL_AGE_HOURS", "0")
    monkeypatch.setenv("MIN_LIQUIDITY_USD", "100000")
    pair = _pair(liquidity_usd=1000)
    ok, _ = token_filter_ok(pair)
    assert not ok


def test_rugcheck_summary_danger_fails():
    report = summary_from_payload(
        {
            "score_normalised": 20,
            "risks": [{"name": "Mint authority", "level": "danger", "value": "yes"}],
        }
    )
    assert not report.ok
    assert any("danger" in r for r in report.reasons)


def test_rugcheck_summary_high_score_fails():
    report = summary_from_payload({"score_normalised": 80, "risks": []})
    assert not report.ok


def test_merge_goplus_fallback_to_rugcheck():
    goplus = SafetyReport(ok=False, reasons=["GoPlus verisi yok"])
    rug = SafetyReport(ok=True, reasons=[])
    merged = _merge_solana_safety(goplus, rug)
    assert merged.ok


def test_merge_strict_rugcheck_blocks():
    goplus = SafetyReport(ok=True, reasons=[])
    rug = SafetyReport(ok=False, reasons=["RugCheck skor yüksek (80>45)"])
    merged = _merge_solana_safety(goplus, rug)
    assert not merged.ok


def test_helius_alpha_count(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "test-key")
    monkeypatch.setenv("ALPHA_WALLETS", "Wallet1,Wallet2")

    def fake_get(url, params=None, timeout=20):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "Wallet1" in url:
            resp.json.return_value = [{"timestamp": time.time(), "tokenTransfers": [{"mint": "T1"}]}]
        else:
            resp.json.return_value = []
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get
    pair = _pair(token_address="T1")
    count = estimate_wallet_buyers(pair, client=client)
    assert count == 1
