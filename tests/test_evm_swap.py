from unittest.mock import MagicMock

import pytest

from hibrit_trader.evm_swap import USDC, get_quote


def test_evm_get_quote():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "sellAmount": "1000000",
        "buyAmount": "5000000000000000000",
        "transaction": {"to": "0x" + "a" * 40, "data": "0x", "gas": "200000"},
    }
    mock_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = mock_resp
    q = get_quote(
        client, "base", USDC["base"], "0x" + "b" * 40,
        1_000_000, "0x" + "c" * 40, 100, "test-key",
    )
    assert q["buyAmount"] == "5000000000000000000"


def test_evm_quote_empty_raises():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"transaction": {}}
    mock_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = mock_resp
    with pytest.raises(ValueError, match="boş"):
        get_quote(
            client, "arbitrum", USDC["arbitrum"], "0xtoken",
            1_000_000, "0xtaker", 100, "key",
        )
