"""Canlı broker — Phantom cüzdan imzası ile Jupiter SOL swap (sunucu key yok)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import httpx
from solana.rpc.api import Client

from hibrit_trader.config import Settings
from hibrit_trader.jupiter import (
    LAMPORTS_PER_SOL,
    SOL_MINT,
    build_swap_tx,
    fetch_sol_price_usd,
    get_quote,
    usd_to_lamports,
)
from hibrit_trader.killswitch import notify
from hibrit_trader.live_sim import fetch_token_decimals
from hibrit_trader.paper import Position, Trade, _now_iso
from hibrit_trader.phantom_trade import PhantomPendingTrade, phantom_queue
from hibrit_trader.scanner import Pair

log = logging.getLogger(__name__)


class PhantomLiveBroker:
    """Solana canlı işlem — SOL paritesi, swap tx Phantom ile imzalanır."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state_path = Path("data/phantom_live_state.json")
        self.trades_path = Path("data/phantom_live_trades.jsonl")
        self._rpc = Client(settings.rpc["solana"])
        self.phantom_pubkey: str | None = None
        self._deployable_usd: float = 0.0
        self.positions: list[Position] = []
        self.realized_pnl: float = 0.0
        self.trades: list[Trade] = []
        self._load()

    @property
    def balance(self) -> float:
        locked = sum(p.cost_usd for p in self.positions)
        return max(0.0, self._deployable_usd - locked)

    def set_phantom(self, pubkey: str, deployable_usd: float) -> None:
        self.phantom_pubkey = pubkey
        self._deployable_usd = float(deployable_usd)

    def clear_phantom(self) -> None:
        self.phantom_pubkey = None
        self._deployable_usd = 0.0

    def supports_chain(self, chain: str) -> bool:
        return chain == "solana" and bool(self.phantom_pubkey)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text())
        self.realized_pnl = float(data.get("realized_pnl", 0.0))
        self.phantom_pubkey = data.get("phantom_pubkey")
        self._deployable_usd = float(
            data.get("deployable_usd", data.get("usdc_balance", 0.0))
        )
        self.positions = [Position(**p) for p in data.get("positions", [])]
        if self.trades_path.exists():
            self.trades = [
                Trade(**json.loads(line))
                for line in self.trades_path.read_text().splitlines()
                if line.strip()
            ]

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "realized_pnl": self.realized_pnl,
                    "phantom_pubkey": self.phantom_pubkey,
                    "deployable_usd": self._deployable_usd,
                    "positions": [asdict(p) for p in self.positions],
                },
                indent=2,
            )
        )

    def _append_trade(self, trade: Trade) -> None:
        self.trades.append(trade)
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trades_path.open("a") as f:
            f.write(json.dumps(asdict(trade)) + "\n")

    def _notify(self, msg: str) -> None:
        log.info(msg)
        notify(msg, self.settings.telegram_bot_token, self.settings.telegram_chat_id)

    def _enqueue(self, kind: str, tx_b64: str, meta: dict) -> None:
        trade_id = phantom_queue.enqueue(kind, tx_b64, meta)
        raise PhantomPendingTrade(trade_id)

    def buy(self, pair: Pair, usd: float, score: float) -> Position:
        if pair.chain != "solana":
            raise ValueError(f"Phantom yalnızca Solana: {pair.chain}")
        if not self.phantom_pubkey:
            raise ValueError("Phantom cüzdan bağlı değil")
        if usd > self.settings.max_position_usd:
            raise ValueError(f"Pozisyon limiti: ${self.settings.max_position_usd}")
        if usd > self.balance:
            raise ValueError(f"SOL bakiyesi yetersiz: ${self.balance:.2f} < ${usd:.2f}")

        with httpx.Client() as http:
            sol_price = fetch_sol_price_usd(http)
            lamports = usd_to_lamports(usd, sol_price)
            quote = get_quote(
                http, SOL_MINT, pair.token_address, lamports, self.settings.max_slippage_bps
            )
            tx_b64 = build_swap_tx(http, quote, self.phantom_pubkey)
            dec = fetch_token_decimals(http, "solana", pair.token_address)
            in_lamports = int(quote["inAmount"])
            cost_usd = in_lamports / LAMPORTS_PER_SOL * sol_price

        self._enqueue(
            "buy",
            tx_b64,
            {
                "pair_name": pair.name,
                "chain": pair.chain,
                "token_address": pair.token_address,
                "pool_address": pair.pool_address,
                "entry_price": pair.price_usd,
                "usd": usd,
                "score": score,
                "out_amount": int(quote["outAmount"]),
                "in_amount": in_lamports,
                "cost_usd": cost_usd,
                "token_decimals": dec,
                "sol_price_usd": sol_price,
            },
        )
        raise RuntimeError("unreachable")

    def complete_trade(self, trade_id: str, signature: str) -> dict:
        pending = phantom_queue.take(trade_id)
        if not pending:
            raise ValueError(f"Bekleyen işlem yok: {trade_id}")

        meta = pending.meta
        if pending.kind == "buy":
            dec = int(meta.get("token_decimals", 6))
            out_raw = int(meta["out_amount"])
            cost = float(meta["cost_usd"])
            amount_token = out_raw / (10**dec)
            entry_price = cost / amount_token if amount_token else float(meta["entry_price"])
            pos = Position(
                pair_name=meta["pair_name"],
                chain=meta["chain"],
                token_address=meta["token_address"],
                pool_address=meta["pool_address"],
                entry_price=entry_price,
                amount_token=amount_token,
                cost_usd=cost,
                opened_at=_now_iso(),
                entry_score=float(meta["score"]),
                amount_raw=out_raw,
            )
            self._deployable_usd = max(0.0, self._deployable_usd - cost)
            self.positions.append(pos)
            self._save()
            self._notify(f"🟢 ALIM [phantom/SOL] {pos.pair_name} ${cost:.2f} sig={signature[:8]}...")
            return {"ok": True, "kind": "buy", "signature": signature}

        if pending.kind == "sell":
            proceeds = float(meta["proceeds_usd"])
            cost = float(meta["cost_usd"])
            pnl = proceeds - cost
            trade = Trade(
                pair_name=meta["pair_name"],
                chain=meta["chain"],
                entry_price=float(meta["entry_price"]),
                exit_price=proceeds / float(meta["amount_token"]) if meta["amount_token"] else 0,
                cost_usd=cost,
                proceeds_usd=proceeds,
                pnl_usd=pnl,
                opened_at=meta["opened_at"],
                closed_at=_now_iso(),
                exit_reason=meta.get("reason", "phantom"),
            )
            self.realized_pnl += pnl
            self._deployable_usd += proceeds
            pool = meta["pool_address"]
            self.positions = [p for p in self.positions if p.pool_address != pool]
            self._append_trade(trade)
            self._save()
            self._notify(
                f"🔴 SATIŞ [phantom/SOL] {trade.pair_name} PnL ${pnl:+.2f} sig={signature[:8]}..."
            )
            return {"ok": True, "kind": "sell", "signature": signature}

        raise ValueError(f"Bilinmeyen işlem türü: {pending.kind}")

    def sell(self, pos: Position, current_price: float, liquidity_usd: float, reason: str) -> Trade:
        if not self.phantom_pubkey:
            raise ValueError("Phantom cüzdan bağlı değil")
        with httpx.Client() as http:
            dec = fetch_token_decimals(http, "solana", pos.token_address)
            amount_raw = pos.amount_raw or int(pos.amount_token * (10**dec))
            sol_price = fetch_sol_price_usd(http)
            quote = get_quote(
                http,
                pos.token_address,
                SOL_MINT,
                amount_raw,
                self.settings.max_slippage_bps,
            )
            tx_b64 = build_swap_tx(http, quote, self.phantom_pubkey)
            out_lamports = int(quote["outAmount"])
            proceeds_usd = out_lamports / LAMPORTS_PER_SOL * sol_price

        self._enqueue(
            "sell",
            tx_b64,
            {
                "pair_name": pos.pair_name,
                "chain": pos.chain,
                "pool_address": pos.pool_address,
                "token_address": pos.token_address,
                "entry_price": pos.entry_price,
                "amount_token": pos.amount_token,
                "cost_usd": pos.cost_usd,
                "opened_at": pos.opened_at,
                "out_amount": out_lamports,
                "proceeds_usd": proceeds_usd,
                "reason": reason,
            },
        )
        raise RuntimeError("unreachable")

    def sell_partial(
        self,
        pos: Position,
        fraction: float,
        current_price: float,
        liquidity_usd: float,
        reason: str,
    ) -> Trade:
        log.warning("Phantom partial sell — tam satış (%.0f%%)", fraction * 100)
        return self.sell(pos, current_price, liquidity_usd, f"{reason} (phantom full)")

    @staticmethod
    def unrealized_pnl(pos: Position, current_price: float) -> float:
        return pos.amount_token * current_price - pos.cost_usd

    def summary(self) -> dict:
        wins = sum(1 for t in self.trades if t.pnl_usd > 0)
        total = len(self.trades)
        return {
            "balance": round(self.balance, 2),
            "phantom_connected": bool(self.phantom_pubkey),
            "phantom_address": self.phantom_pubkey,
            "quote_pair": "SOL",
            "live_chains": ["solana"] if self.phantom_pubkey else [],
            "open_positions": len(self.positions),
            "realized_pnl": round(self.realized_pnl, 2),
            "trade_count": total,
            "win_rate": round(wins / total * 100, 1) if total else 0.0,
        }
