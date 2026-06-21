"""Jupiter quote vs havuz fiyatı — gerçek slippage geri beslemesi."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from hibrit_trader.config import Settings
from hibrit_trader.jupiter import SOL_MINT, fetch_sol_price_usd, get_quote, usd_to_lamports
from hibrit_trader.live_sim import fetch_pool_price, fetch_token_decimals
from hibrit_trader.scanner import Pair

log = logging.getLogger(__name__)


def _pool_slippage_pct(position_usd: float, liquidity_usd: float) -> float:
    if liquidity_usd <= 0:
        return 5.0
    return min(position_usd / liquidity_usd, 0.05) * 100


def estimate_entry_slippage_pct(
    client: httpx.Client,
    pair: Pair,
    position_usd: float,
    settings: Settings,
) -> tuple[float, str]:
    """Tek yön slippage tahmini; Jupiter vs pool farkını edge'e yazar."""
    pool_slip = _pool_slippage_pct(position_usd, pair.liquidity_usd)
    if pair.chain != "solana" or not settings.paper_live_quotes:
        return round(pool_slip * 2, 2), "pool_model"

    pool_price = fetch_pool_price(client, pair.chain, pair.pool_address) or pair.price_usd
    if pool_price <= 0:
        return round(pool_slip * 2, 2), "pool_model"

    dec = fetch_token_decimals(client, pair.chain, pair.token_address)
    try:
        sol_price = fetch_sol_price_usd(client)
        lamports = usd_to_lamports(position_usd, sol_price)
    except (httpx.HTTPError, ValueError):
        return round(pool_slip * 2, 2), "pool_model"

    if lamports <= 0:
        return round(pool_slip * 2, 2), "pool_model"

    try:
        quote = get_quote(client, SOL_MINT, pair.token_address, lamports, settings.max_slippage_bps)
        out_raw = int(quote["outAmount"])
        if out_raw <= 0:
            raise ValueError("zero out")
        jup_price = position_usd / (out_raw / (10**dec))
        delta_pct = abs(jup_price - pool_price) / pool_price * 100
        impact = float(quote.get("priceImpactPct") or 0)
        extra = max(delta_pct, abs(impact), pool_slip)
        return round(extra * 2, 2), "jupiter_vs_pool"
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("Jupiter giriş slippage yok %s: %s", pair.token_address[:8], exc)
        return round(pool_slip * 2, 2), "pool_fallback"
