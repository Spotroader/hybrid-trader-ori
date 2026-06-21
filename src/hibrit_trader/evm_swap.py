"""0x Swap API — EVM canlı yürütme (Base / Arbitrum / BSC). API key ücretsiz: 0x.org"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from eth_account import Account
from web3 import Web3

log = logging.getLogger(__name__)

ZEROX_API = "https://api.0x.org"

EVM_CHAINS = frozenset({"base", "arbitrum", "bsc"})

CHAIN_ID = {"base": 8453, "arbitrum": 42161, "bsc": 56}

USDC = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "bsc": "0x8AC76a51cc950d9822D686bF4cD227B93280245c",
}


def load_account(private_key_hex: str) -> Account:
    key = private_key_hex.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    return Account.from_key(key)


def _headers(api_key: str) -> dict:
    h = {"0x-version": "v2"}
    if api_key:
        h["0x-api-key"] = api_key
    return h


def get_quote(
    http: httpx.Client,
    chain: str,
    sell_token: str,
    buy_token: str,
    sell_amount: int,
    taker: str,
    slippage_bps: int,
    api_key: str,
) -> dict:
    url = f"{ZEROX_API}/swap/permit2/quote"
    params = {
        "chainId": str(CHAIN_ID[chain]),
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmount": str(sell_amount),
        "taker": taker,
        "slippageBps": str(slippage_bps),
    }
    resp = http.get(url, params=params, headers=_headers(api_key), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("buyAmount"):
        raise ValueError("0x quote boş yanıt")
    return data


def sign_and_send(web3: Web3, account: Account, quote: dict) -> str:
    tx = quote["transaction"]
    nonce = web3.eth.get_transaction_count(account.address)
    built = {
        "from": account.address,
        "to": Web3.to_checksum_address(tx["to"]),
        "data": tx["data"],
        "value": int(tx.get("value", 0)),
        "gas": int(tx.get("gas", 500_000)),
        "nonce": nonce,
        "chainId": web3.eth.chain_id,
    }
    if "gasPrice" in tx:
        built["gasPrice"] = int(tx["gasPrice"])
    elif "maxFeePerGas" in tx:
        built["maxFeePerGas"] = int(tx["maxFeePerGas"])
        built["maxPriorityFeePerGas"] = int(tx.get("maxPriorityFeePerGas", 0))
    else:
        built["gasPrice"] = web3.eth.gas_price

    signed = account.sign_transaction(built)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise RuntimeError(f"EVM işlem başarısız: {tx_hash.hex()}")
    return tx_hash.hex()


def swap_usdc_to_token(
    http: httpx.Client,
    web3: Web3,
    account: Account,
    chain: str,
    token_address: str,
    usd: float,
    slippage_bps: int,
    api_key: str,
) -> dict:
    sell_amount = int(usd * 1_000_000)
    quote = get_quote(
        http, chain, USDC[chain], token_address, sell_amount,
        account.address, slippage_bps, api_key,
    )
    tx_hash = sign_and_send(web3, account, quote)
    return {
        "tx_hash": tx_hash,
        "sell_amount": int(quote["sellAmount"]),
        "buy_amount": int(quote["buyAmount"]),
    }


def swap_token_to_usdc(
    http: httpx.Client,
    web3: Web3,
    account: Account,
    chain: str,
    token_address: str,
    amount_raw: int,
    slippage_bps: int,
    api_key: str,
) -> dict:
    quote = get_quote(
        http, chain, token_address, USDC[chain], amount_raw,
        account.address, slippage_bps, api_key,
    )
    tx_hash = sign_and_send(web3, account, quote)
    return {
        "tx_hash": tx_hash,
        "sell_amount": int(quote["sellAmount"]),
        "buy_amount": int(quote["buyAmount"]),
    }
