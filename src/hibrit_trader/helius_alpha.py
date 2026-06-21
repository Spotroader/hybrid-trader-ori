"""Helius — yapılandırılmış alpha cüzdanların son swap aktivitesi (Faz 8b)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

_CACHE: dict[str, tuple[float, int]] = {}
_CACHE_TTL = 300.0
_LOOKBACK_SEC = 86400.0


def helius_api_key() -> str:
    from hibrit_trader.alpha_config import resolve_helius_api_key

    return resolve_helius_api_key()


def helius_enabled() -> bool:
    return bool(helius_api_key())


def alpha_scan_limit() -> int:
    return max(1, min(25, int(os.getenv("ALPHA_WALLET_SCAN_LIMIT", "15"))))


def alpha_tracking_status() -> dict:
    """Panel / startup — Helius + cüzdan listesi durumu."""
    from hibrit_trader.alpha_config import alpha_config_status

    st = alpha_config_status()
    st["scan_limit"] = alpha_scan_limit()
    return st


def _cache_get(key: str) -> int | None:
    row = _CACHE.get(key)
    if not row:
        return None
    ts, count = row
    if time.time() - ts > _CACHE_TTL:
        return None
    return count


def _cache_set(key: str, count: int) -> None:
    _CACHE[key] = (time.time(), count)


def _tx_involves_mint(tx: dict, mint: str) -> bool:
    mint_l = mint.lower()
    for field in ("tokenTransfers", "accountData"):
        for item in tx.get(field) or []:
            if isinstance(item, dict):
                for k in ("mint", "tokenAddress", "token"):
                    val = item.get(k)
                    if isinstance(val, str) and val.lower() == mint_l:
                        return True
    meta = tx.get("events") or {}
    swap = meta.get("swap") or {}
    for leg in (swap.get("tokenInputs") or []) + (swap.get("tokenOutputs") or []):
        if isinstance(leg, dict):
            m = leg.get("mint")
            if isinstance(m, str) and m.lower() == mint_l:
                return True
    description = str(tx.get("description") or "")
    return mint_l[:8] in description.lower()


def _wallet_bought_token(client: httpx.Client, wallet: str, mint: str, api_key: str) -> bool:
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
    params = {"api-key": api_key, "limit": 20, "type": "SWAP"}
    resp = client.get(url, params=params, timeout=20)
    resp.raise_for_status()
    now = time.time()
    for tx in resp.json() or []:
        ts = tx.get("timestamp")
        if isinstance(ts, (int, float)) and now - float(ts) > _LOOKBACK_SEC:
            continue
        if _tx_involves_mint(tx, mint):
            return True
    return False


def count_recent_alpha_buyers(
    client: httpx.Client,
    mint: str,
    wallets: list[str],
    *,
    lookback_sec: float | None = None,
) -> int | None:
    """Son N sn içinde mint ile swap yapan yapılandırılmış cüzdan sayısı. Helius yoksa None."""
    api_key = helius_api_key()
    if not api_key or not wallets:
        return None

    window = float(lookback_sec if lookback_sec is not None else _LOOKBACK_SEC)
    cache_key = f"{mint}:{int(window)}:{'|'.join(sorted(wallets[:alpha_scan_limit()]))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    count = 0
    limit = alpha_scan_limit()
    now = time.time()
    for wallet in wallets[:limit]:
        try:
            url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
            params = {"api-key": api_key, "limit": 25, "type": "SWAP"}
            resp = client.get(url, params=params, timeout=20)
            resp.raise_for_status()
            for tx in resp.json() or []:
                ts = tx.get("timestamp")
                if isinstance(ts, (int, float)) and now - float(ts) > window:
                    continue
                if _tx_involves_mint(tx, mint):
                    count += 1
                    break
        except httpx.HTTPError:
            continue
        time.sleep(0.15)

    _cache_set(cache_key, count)
    return count
