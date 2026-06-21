"""Helius + ALPHA_WALLETS — on-chain cüzdan sayımı wiring."""

import time
from unittest.mock import MagicMock

from hibrit_trader.helius_alpha import alpha_tracking_status
from hibrit_trader.smart_money import scan_whale_accumulation, wallet_buyer_info
from tests.test_faz8 import _pair


def test_wallet_buyer_proxy_without_helius(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_WALLETS", raising=False)
    monkeypatch.setenv("ALPHA_RPC_FALLBACK", "0")
    monkeypatch.setenv("ALPHA_WALLETS_FILE", "/nonexistent/alpha_wallets.txt")
    pair = _pair(txns_h1=500, chg_h1=8, chg_m5=2, vol_h1=200_000, liquidity_usd=100_000)
    count, src = wallet_buyer_info(pair, client=MagicMock())
    assert src == "proxy"
    assert count >= 2


def test_wallet_buyer_helius(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "test-key")
    monkeypatch.setenv("ALPHA_WALLETS", "Wallet1,Wallet2")

    def fake_get(url, params=None, timeout=20):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "Wallet1" in url:
            resp.json.return_value = [
                {"timestamp": time.time(), "tokenTransfers": [{"mint": "T1"}]}
            ]
        else:
            resp.json.return_value = []
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get
    pair = _pair(token_address="T1")
    count, src = wallet_buyer_info(pair, client=client)
    assert src == "helius"
    assert count == 1


def test_scan_whale_passes_client(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "k")
    monkeypatch.setenv("ALPHA_WALLETS", "W1")

    def fake_count(client, mint, wallets, **kwargs):
        assert mint == "T1"
        return 3

    monkeypatch.setattr(
        "hibrit_trader.helius_alpha.count_recent_alpha_buyers",
        fake_count,
    )
    pair = _pair(token_address="T1", chg_h1=5, chg_m5=2, vol_h1=300_000, vol_h24=500_000)
    rows = scan_whale_accumulation([pair], client=MagicMock())
    assert rows[0]["wallet_count"] == 3
    assert rows[0]["wallet_source"] in ("helius", "copy")


def test_alpha_tracking_status(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "k")
    monkeypatch.setenv("ALPHA_WALLETS", "A,B")
    st = alpha_tracking_status()
    assert st["on_chain"] is True
    assert st["alpha_wallets"] == 2
