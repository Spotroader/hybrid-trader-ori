import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from hibrit_trader.jupiter import USDC_MINT, build_swap_tx, get_quote


def test_get_quote_parses_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"inAmount": "1000000", "outAmount": "5000000000"}
    mock_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = mock_resp
    q = get_quote(client, USDC_MINT, "TokenMint", 1_000_000, 100)
    assert q["outAmount"] == "5000000000"


def test_get_quote_empty_raises():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = mock_resp
    with pytest.raises(ValueError, match="boş"):
        get_quote(client, USDC_MINT, "TokenMint", 1_000_000, 100)


def test_build_swap_tx():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"swapTransaction": "abc123base64"}
    mock_resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = mock_resp
    tx = build_swap_tx(client, {"inAmount": "1", "outAmount": "2"}, "Pubkey111")
    assert tx == "abc123base64"
