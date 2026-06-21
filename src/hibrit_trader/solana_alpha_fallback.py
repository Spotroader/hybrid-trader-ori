"""Solana RPC ile alpha cüzdan swap sayımı — Helius ücretli; varsayılan $0 public RPC."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

_CACHE: dict[str, tuple[float, int]] = {}
_CACHE_TTL = 300.0
_LOOKBACK_SEC = 86400.0

# Ücretsiz public endpoint'ler (rate limit düşük — SOLANA_RPC_URL ile override önerilir)
_DEFAULT_RPC_URLS = (
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
    "https://rpc.ankr.com/solana",
)


def _rpc_urls() -> list[str]:
    primary = os.getenv("SOLANA_RPC_URL", "").strip()
    extra = [
        u.strip()
        for u in os.getenv("SOLANA_RPC_FALLBACK_URLS", "").split(",")
        if u.strip()
    ]
    out: list[str] = []
    seen: set[str] = set()
    for url in ([primary] if primary else []) + extra + list(_DEFAULT_RPC_URLS):
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out or list(_DEFAULT_RPC_URLS)


def _rpc_post(client: httpx.Client, method: str, params: list[Any]) -> Any:
    last_err: Exception | None = None
    for url in _rpc_urls():
        try:
            resp = client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=25,
            )
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:
                raise httpx.HTTPError(str(body["error"]))
            return body.get("result")
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    raise httpx.HTTPError("no RPC endpoints configured")


def _wallet_bought_mint(tx: dict, wallet: str, mint: str) -> bool:
    mint_l = mint.lower()
    wallet_l = wallet.lower()
    meta = tx.get("meta") or {}
    for bal in meta.get("postTokenBalances") or []:
        if str(bal.get("mint", "")).lower() != mint_l:
            continue
        owner = (bal.get("owner") or "").lower()
        if owner == wallet_l:
            pre_amt = 0.0
            idx = bal.get("accountIndex")
            for pre in meta.get("preTokenBalances") or []:
                if pre.get("accountIndex") == idx and str(pre.get("mint", "")).lower() == mint_l:
                    ui = pre.get("uiTokenAmount") or {}
                    pre_amt = float(ui.get("uiAmount") or 0)
            post_ui = bal.get("uiTokenAmount") or {}
            post_amt = float(post_ui.get("uiAmount") or 0)
            if post_amt > pre_amt:
                return True
    return False


def count_recent_alpha_buyers_rpc(
    client: httpx.Client,
    mint: str,
    wallets: list[str],
    *,
    lookback_sec: float | None = None,
) -> int | None:
    """Public Solana RPC — $0 alpha sayımı (Helius ücretli alternatif)."""
    if not wallets or not mint:
        return None

    from hibrit_trader.helius_alpha import alpha_scan_limit

    window = float(lookback_sec if lookback_sec is not None else _LOOKBACK_SEC)
    limit_w = alpha_scan_limit()
    cache_key = f"rpc:{mint}:{int(window)}:{'|'.join(sorted(wallets[:limit_w]))}"
    row = _CACHE.get(cache_key)
    if row and time.time() - row[0] < _CACHE_TTL:
        return row[1]

    count = 0
    now = time.time()
    for wallet in wallets[:limit_w]:
        try:
            sigs = _rpc_post(
                client,
                "getSignaturesForAddress",
                [wallet, {"limit": 15}],
            )
            for item in sigs or []:
                bt = item.get("blockTime")
                if isinstance(bt, int) and now - bt > window:
                    continue
                sig = item.get("signature")
                if not sig:
                    continue
                tx = _rpc_post(
                    client,
                    "getTransaction",
                    [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                )
                if tx and _wallet_bought_mint(tx, wallet, mint):
                    count += 1
                    break
            time.sleep(0.12)
        except httpx.HTTPError:
            continue

    _CACHE[cache_key] = (time.time(), count)
    return count
