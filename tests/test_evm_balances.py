"""EVM cüzdan bakiyesi fetch testleri."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hibrit_trader.evm_balances import _fmt_amount, fetch_chain_balances, fetch_portfolio


def test_fmt_amount():
    assert _fmt_amount(1_000_000, 6) == 1.0
    assert _fmt_amount(10**18, 18) == 1.0


@patch("hibrit_trader.evm_balances.Web3")
def test_fetch_chain_balances_native_only(mock_web3_cls):
    mock_web3 = MagicMock()
    mock_web3.is_connected.return_value = True
    mock_web3.eth.get_balance.return_value = 10**18
    mock_contract = MagicMock()
    mock_contract.functions.balanceOf.return_value.call.return_value = 0
    mock_web3.eth.contract.return_value = mock_contract
    mock_web3_cls.return_value = mock_web3
    mock_web3_cls.to_checksum_address.side_effect = lambda x: x

    result = fetch_chain_balances("http://rpc.test", "0xabc", "base")

    assert len(result) == 1
    assert result[0]["symbol"] == "ETH"
    assert result[0]["balance"] == 1.0


@patch("hibrit_trader.evm_balances.fetch_chain_balances")
def test_fetch_portfolio_aggregates(mock_fetch):
    def side_effect(rpc, addr, chain):
        if chain == "base":
            return [{"symbol": "ETH", "balance": 0.5, "decimals": 18}]
        if chain == "bsc":
            return [{"symbol": "BNB", "balance": 1.0, "decimals": 18}]
        return []

    mock_fetch.side_effect = side_effect
    out = fetch_portfolio(
        {"base": "http://b", "arbitrum": "http://a", "bsc": "http://c"},
        "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
    )
    assert out["address"]
    assert out["chains"]["base"]["tokens"][0]["symbol"] == "ETH"
    assert out["chains"]["arbitrum"]["tokens"] == []
    assert out["chains"]["bsc"]["tokens"][0]["symbol"] == "BNB"
    assert mock_fetch.call_count == 3
