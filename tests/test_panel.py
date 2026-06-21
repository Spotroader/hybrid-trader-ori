"""Panel HTML ve static JS doğrulama."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from hibrit_trader.config import CHAIN_ENTRY_PRIORITY

import pytest
from fastapi.testclient import TestClient

from hibrit_trader import panel

STATIC_JS = Path(__file__).resolve().parents[1] / "src" / "hibrit_trader" / "static" / "panel.js"


@pytest.fixture
def client():
    return TestClient(panel.app)


def test_index_serves_panel_js_reference(client):
    r = client.get("/")
    assert r.status_code == 200
    assert '/static/panel.js' in r.text
    assert '/static/panel.css' in r.text
    assert '/static/panel-quantum.css' in r.text
    assert 'data-theme' in r.text
    assert "onclick=" not in r.text
    assert 'walletHoldings' in r.text
    assert 'holdingsBody' in r.text
    assert 'runScanBtn' in r.text
    assert 'scanPanel' in r.text
    assert 'hudCockpit' in r.text
    assert 'hudMetrics' in r.text
    assert 'qc-dash' in r.text
    assert 'trendPanel' in r.text
    assert 'HYBRID' in r.text
    assert 'Hybrid Trade' in r.text
    assert 'HIBRIT_BOT' not in r.text
    assert 'saitoBrainVisual' in r.text
    assert 'saitoHub' in r.text
    assert 'positionsPanel' in r.text
    assert 'hudPositionUsd' in r.text
    assert 'hudPositionMeta' in r.text
    assert 'positionsTotalBar' in r.text
    assert 'positionsTotalCost' in r.text
    assert 'Pozisyon</span>' in r.text
    assert 'liveSimTags' in r.text
    assert 'phantomBtn' in r.text
    assert 'killBtn' not in r.text


def test_static_panel_quantum_css_served(client):
    r = client.get("/static/panel-quantum.css")
    assert r.status_code == 200
    assert ".qc-dash" in r.text
    assert ".saito-core" in r.text


def test_static_panel_css_served(client):
    r = client.get("/static/panel.css")
    assert r.status_code == 200
    assert "--accent" in r.text
    assert "data-theme" in r.text


def test_static_panel_js_served(client):
    r = client.get("/static/panel.js")
    assert r.status_code == 200
    body = r.text
    assert "connectPhantom" in body
    assert "phantomBtn" in body
    assert "refreshSolPortfolio" in body or "processPhantomPending" in body
    assert "function shortAddr" in body
    assert "runAdvancedScan" in body


def test_api_scan_modes(client):
    r = client.get("/api/scan/modes")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 6
    assert any(m["id"] == "cex" for m in data)


def test_api_scan_run_mock(client, monkeypatch):
    fake = {
        "modes": ["cex"],
        "social": {"enabled": False},
        "count": 1,
        "results": [{"symbol": "BTC", "exchange": "binance", "score": 80, "tam_isabet": True, "reason": "test"}],
    }
    monkeypatch.setattr(panel, "run_advanced_scan", lambda modes, limit=15: fake)
    r = client.post("/api/scan", json={"modes": ["cex"], "limit": 5})
    assert r.status_code == 200
    assert r.json()["results"][0]["symbol"] == "BTC"


def test_api_wallet_portfolio(client, monkeypatch):
    addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"

    def fake_portfolio(rpc_map, address):
        assert address == addr
        return {
            "address": address,
            "chains": {
                "base": {
                    "chain": "base",
                    "label": "Base",
                    "tokens": [{"symbol": "ETH", "balance": 1.0, "decimals": 18}],
                    "error": None,
                },
            },
        }

    monkeypatch.setattr(panel, "fetch_portfolio", fake_portfolio)
    r = client.get("/api/wallet/portfolio", params={"address": addr})
    assert r.status_code == 200
    data = r.json()
    assert data["chains"]["base"]["tokens"][0]["symbol"] == "ETH"


def test_api_wallet_portfolio_invalid_address(client):
    r = client.get(
        "/api/wallet/portfolio",
        params={"address": "0xgggggggggggggggggggggggggggggggggggggggg"},
    )
    assert r.status_code == 400


def test_wallet_logo_served(client):
    r = client.get("/static/wallet-logo.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")


def test_api_state_live_sim(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert "live_sim" in data
    assert data["live_sim"]["trade_execution"] in ("paper", "live")
    assert "description_tr" in data["live_sim"]


def test_api_state_chain_opportunities(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert "chain_opportunities" in data
    chains = [c["chain"] for c in data["chain_opportunities"]]
    assert chains == sorted(chains, key=lambda c: (
        -max((w["score"] for w in data["watchlist"] if w["chain"] == c), default=0),
        CHAIN_ENTRY_PRIORITY.get(c, 99),
        c,
    ))


def test_panel_js_syntax_valid():
    js = STATIC_JS.read_text()
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    proc = subprocess.run(
        [node, "-e", f"new Function({js!r}); console.log('OK')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
