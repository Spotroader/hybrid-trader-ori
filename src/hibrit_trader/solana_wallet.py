"""Solana cüzdan bakiyesi — Phantom panel (SOL paritesi, Jupiter)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from solders.pubkey import Pubkey

from hibrit_trader.jupiter import (
    SOL_GAS_RESERVE,
    SOL_MINT,
    USDC_MINT,
    fetch_sol_price_usd,
)

log = logging.getLogger(__name__)

SOL_DECIMALS = 9


def is_valid_solana_address(address: str) -> bool:
    try:
        Pubkey.from_string(address.strip())
        return True
    except Exception:
        return False


def _rpc_post(client: httpx.Client, rpc_url: str, method: str, params: list) -> Any:
    resp = client.post(
        rpc_url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=25,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("result")


def _sol_balance(client: httpx.Client, rpc_url: str, pubkey: str) -> float:
    result = _rpc_post(client, rpc_url, "getBalance", [pubkey, {"commitment": "confirmed"}])
    lamports = int(result.get("value", 0))
    return lamports / (10 ** SOL_DECIMALS)


def _usdc_balance(client: httpx.Client, rpc_url: str, pubkey: str) -> float:
    result = _rpc_post(
        client,
        rpc_url,
        "getTokenAccountsByOwner",
        [
            pubkey,
            {"mint": USDC_MINT},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )
    total = 0.0
    for item in result.get("value") or []:
        info = item.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
        token_amount = info.get("tokenAmount") or {}
        ui = token_amount.get("uiAmount")
        if ui is not None:
            total += float(ui)
    return total


def fetch_sol_portfolio(rpc_url: str, pubkey: str, *, client: httpx.Client | None = None) -> dict:
    """SOL bakiyesi + USD karşılığı — alım boyutu SOL paritesinden."""
    if not is_valid_solana_address(pubkey):
        raise ValueError("Geçersiz Solana adresi")

    own = client is None
    http = client or httpx.Client()
    try:
        sol = _sol_balance(http, rpc_url, pubkey)
        usdc = _usdc_balance(http, rpc_url, pubkey)
        try:
            sol_price_usd = fetch_sol_price_usd(http)
        except Exception as e:
            log.warning("SOL USD fiyatı alınamadı, fallback: %s", e)
            sol_price_usd = 150.0
    finally:
        if own:
            http.close()

    tradeable_sol = max(0.0, sol - SOL_GAS_RESERVE)
    deployable_usd = round(tradeable_sol * sol_price_usd, 2)
    return {
        "address": pubkey,
        "chain": "solana",
        "sol": round(sol, 6),
        "tradeable_sol": round(tradeable_sol, 6),
        "sol_price_usd": round(sol_price_usd, 4),
        "usdc": round(usdc, 2),
        "deployable_usd": deployable_usd,
        "quote_pair": "SOL",
        "mints": {"sol": SOL_MINT, "usdc": USDC_MINT},
    }
