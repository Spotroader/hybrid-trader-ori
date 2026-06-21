"""Solana cüzdan bakiyesi testleri."""

from __future__ import annotations

import pytest

from hibrit_trader.solana_wallet import fetch_sol_portfolio, is_valid_solana_address

# Well-known system program — valid base58 pubkey format
SOL_PUBKEY = "11111111111111111111111111111112"


def test_is_valid_solana_address():
    assert is_valid_solana_address(SOL_PUBKEY)
    assert not is_valid_solana_address("not-a-pubkey")
    assert not is_valid_solana_address("0x742d35Cc6634C0532925a3b844Bc454e4438f44e")


def test_fetch_sol_portfolio_mock(monkeypatch):
    import httpx

    class FakeResp:
        def __init__(self, result):
            self._result = result

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": self._result}

    calls = []

    def fake_post(self, url, json=None, timeout=None, **kwargs):
        calls.append(json["method"])
        if json["method"] == "getBalance":
            return FakeResp({"value": 2_000_000_000})  # 2 SOL
        if json["method"] == "getTokenAccountsByOwner":
            return FakeResp(
                {
                    "value": [
                        {
                            "account": {
                                "data": {
                                    "parsed": {
                                        "info": {
                                            "tokenAmount": {"uiAmount": 150.5},
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            )
        raise AssertionError(json["method"])

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(
        "hibrit_trader.solana_wallet.fetch_sol_price_usd",
        lambda _c: 100.0,
    )
    out = fetch_sol_portfolio("https://rpc.example", SOL_PUBKEY)
    assert out["sol"] == 2.0
    assert out["tradeable_sol"] == round(2.0 - 0.05, 6)
    assert out["deployable_usd"] == round(1.95 * 100.0, 2)
    assert out["quote_pair"] == "SOL"
    assert "getBalance" in calls
