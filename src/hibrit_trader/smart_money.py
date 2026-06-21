"""Smart money / alpha cüzdan — 3+ iyi cüzdan sinyali + balina toplama."""

from __future__ import annotations

import os
from typing import Iterable, Literal

from hibrit_trader.scanner import Pair

MIN_ALPHA_WALLETS = 3
WalletSource = Literal["helius", "rpc", "proxy", "copy", "na"]


def copy_trade_enabled() -> bool:
    return os.getenv("COPY_TRADE_ENABLED", "1") != "0"


def copy_trade_window_sec() -> int:
    return int(os.getenv("COPY_TRADE_WINDOW_SEC", "300"))


def copy_trade_min_wallets() -> int:
    return int(os.getenv("COPY_TRADE_MIN_WALLETS", "2"))


def count_alpha_copy_window(
    pair: Pair,
    *,
    client=None,
    window_sec: int | None = None,
) -> int | None:
    """Kısa pencerede (varsayılan 5 dk) alpha cüzdan cluster — DS öncesi overlap."""
    if pair.chain != "solana" or client is None or _paper_proxy_only():
        return None
    wallets = alpha_wallet_addresses()
    if not wallets:
        return None
    window = float(window_sec if window_sec is not None else copy_trade_window_sec())
    if alpha_on_chain_enabled():
        from hibrit_trader.helius_alpha import count_recent_alpha_buyers

        return count_recent_alpha_buyers(client, pair.token_address, wallets, lookback_sec=window)
    if os.getenv("ALPHA_RPC_FALLBACK", "1") != "0":
        from hibrit_trader.solana_alpha_fallback import count_recent_alpha_buyers_rpc

        return count_recent_alpha_buyers_rpc(
            client, pair.token_address, wallets, lookback_sec=window
        )
    return None


def alpha_wallet_addresses() -> list[str]:
    from hibrit_trader.alpha_config import load_alpha_wallet_addresses

    return load_alpha_wallet_addresses()


def alpha_on_chain_enabled() -> bool:
    from hibrit_trader.helius_alpha import helius_enabled

    return helius_enabled() and bool(alpha_wallet_addresses())


def _vol_spike(pair: Pair) -> float:
    avg_h1 = max(pair.vol_h24 / 24, 1.0)
    return pair.vol_h1 / avg_h1


def _proxy_wallet_buyers(pair: Pair) -> int:
    txn_score = min(3, max(0, pair.txns_h1 // 200))
    vol_score = 1 if _vol_spike(pair) >= 2.2 else 0
    momentum = 1 if pair.chg_h1 > 5 and pair.chg_m5 > 1.5 else 0
    liq_score = 1 if pair.liquidity_usd >= 80_000 else 0
    return min(6, txn_score + vol_score + momentum + liq_score)


def _paper_proxy_only() -> bool:
    """Paper agresif taramada tick başına yüzlerce Solana RPC yapma — proxy yeter."""
    if os.getenv("ALPHA_RPC_SCAN", "0") == "1":
        return False
    return (
        os.getenv("BOT_MODE", "paper").lower() == "paper"
        and os.getenv("PAPER_AGGRESSIVE", "1") != "0"
    )


def wallet_buyer_info(pair: Pair, *, client=None) -> tuple[int, WalletSource]:
    """Cüzdan sayısı + kaynak: Helius / RPC alpha / copy cluster / txns proxy."""
    if client is not None and _paper_proxy_only():
        client = None
    configured = alpha_wallet_addresses()
    if pair.chain == "solana" and configured and client is not None:
        if copy_trade_enabled():
            copy_n = count_alpha_copy_window(pair, client=client)
            copy_min = copy_trade_min_wallets()
            if copy_n is not None and copy_n >= copy_min:
                return copy_n, "copy"
        if alpha_on_chain_enabled():
            from hibrit_trader.helius_alpha import count_recent_alpha_buyers

            on_chain = count_recent_alpha_buyers(client, pair.token_address, configured)
            if on_chain is not None:
                return on_chain, "helius"
        if os.getenv("ALPHA_RPC_FALLBACK", "1") != "0":
            from hibrit_trader.solana_alpha_fallback import count_recent_alpha_buyers_rpc

            rpc_count = count_recent_alpha_buyers_rpc(client, pair.token_address, configured)
            if rpc_count is not None:
                return rpc_count, "rpc"
    if pair.chain != "solana":
        return _proxy_wallet_buyers(pair), "na"
    return _proxy_wallet_buyers(pair), "proxy"


def estimate_wallet_buyers(pair: Pair, *, client=None) -> int:
    count, _ = wallet_buyer_info(pair, client=client)
    return count


def smart_money_entry_ok(
    pair: Pair,
    min_wallets: int = MIN_ALPHA_WALLETS,
    *,
    client=None,
) -> tuple[bool, str]:
    count, src = wallet_buyer_info(pair, client=client)
    if count >= min_wallets:
        label = {"helius": "on-chain", "rpc": "RPC alpha", "copy": "copy cluster", "proxy": "proxy", "na": "—"}.get(
            src, src
        )
        return True, f"alpha {count} cüzdan ({label})"
    return False, f"alpha yetersiz ({count}<{min_wallets})"


def scan_whale_accumulation(
    pairs: Iterable[Pair],
    limit: int = 15,
    *,
    client=None,
) -> list[dict]:
    """Balina + 3+ cüzdan — Helius varsa Sol mint için gerçek alpha sayımı."""
    rows: list[dict] = []
    for pair in pairs:
        wallets, src = wallet_buyer_info(pair, client=client)
        vol_sp = _vol_spike(pair)
        vol_ok = vol_sp >= 1.5
        chg_ok = pair.chg_h1 > 2 or pair.chg_m5 > 1
        buy_signal = wallets >= MIN_ALPHA_WALLETS and vol_ok and chg_ok
        symbol = pair.name.split("/")[0].strip() if "/" in pair.name else pair.name[:12]
        score = min(
            100.0,
            25 * min(wallets / 5, 1)
            + 25 * min(vol_sp / 3, 1)
            + 20 * min(pair.liquidity_usd / 500_000, 1)
            + 15 * min(max(pair.chg_h1, 0) / 15, 1)
            + (15 if buy_signal else 0),
        )
        src_label = {"helius": "Helius", "rpc": "RPC", "copy": "copy", "proxy": "proxy", "na": "—"}.get(src, src)
        rows.append(
            {
                "symbol": symbol,
                "pair": pair.name,
                "chain": pair.chain,
                "wallet_count": wallets,
                "wallet_source": src,
                "wallet_source_label": src_label,
                "vol_spike": round(vol_sp, 2),
                "liquidity_usd": round(pair.liquidity_usd),
                "chg_h1": round(pair.chg_h1, 1),
                "buy_signal": buy_signal,
                "score": round(score, 1),
                "reason": (
                    f"{wallets} cüzdan ({src_label}) · hacim x{vol_sp:.1f} · H1 {pair.chg_h1:+.1f}%"
                    + (" · AL" if buy_signal else "")
                ),
            }
        )
    rows.sort(key=lambda r: (-r["buy_signal"], -r["score"], -r["wallet_count"]))
    return rows[:limit]
