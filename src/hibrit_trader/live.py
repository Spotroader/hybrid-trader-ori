"""Canlı broker — Solana (Jupiter) + EVM (0x), PaperBroker ile aynı arayüz."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import httpx
from solana.rpc.api import Client
from web3 import Web3

from hibrit_trader.config import Settings
from hibrit_trader.evm_swap import EVM_CHAINS, load_account, swap_token_to_usdc as evm_sell
from hibrit_trader.evm_swap import swap_usdc_to_token as evm_buy
from hibrit_trader.jupiter import (
    load_keypair,
    swap_sol_to_token,
    swap_token_to_sol,
)
from hibrit_trader.live_sim import fetch_token_decimals
from hibrit_trader.killswitch import notify
from hibrit_trader.paper import Position, Trade, _now_iso
from hibrit_trader.scanner import Pair

log = logging.getLogger(__name__)

SOL_DECIMALS = 9
EVM_DECIMALS = 18  # çoğu meme token; kesin değer 0x buyAmount'dan türetilir


class LiveBroker:
    """Çok ağlı canlı broker. Solana key → Jupiter; EVM key + ZEROX_API_KEY → Base/Arbitrum/BSC."""

    def __init__(self, settings: Settings) -> None:
        if not settings.solana_private_key and not settings.evm_private_key:
            raise ValueError("live mod için SOLANA_PRIVATE_KEY veya EVM_PRIVATE_KEY gerekli")
        self.settings = settings
        self.state_path = Path("data/live_state.json")
        self.trades_path = Path("data/live_trades.jsonl")
        self._sol_rpc: Client | None = None
        self._sol_keypair = None
        self._evm_account = None
        self._evm_web3: dict[str, Web3] = {}

        if settings.sol_server_signing_enabled():
            self._sol_keypair = load_keypair(settings.solana_private_key)
            self._sol_rpc = Client(settings.rpc["solana"])
        if settings.evm_private_key:
            self._evm_account = load_account(settings.evm_private_key)
            for chain in EVM_CHAINS:
                self._evm_web3[chain] = Web3(Web3.HTTPProvider(settings.rpc[chain]))

        self.positions: list[Position] = []
        self.realized_pnl: float = 0.0
        self.trades: list[Trade] = []
        self._load()

    def supports_chain(self, chain: str) -> bool:
        return chain in self.settings.live_chains()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text())
        self.realized_pnl = float(data.get("realized_pnl", 0.0))
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
                {"realized_pnl": self.realized_pnl, "positions": [asdict(p) for p in self.positions]},
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

    def buy(self, pair: Pair, usd: float, score: float) -> Position:
        if not self.supports_chain(pair.chain):
            raise ValueError(f"Ağ desteklenmiyor veya key eksik: {pair.chain}")
        if usd > self.settings.max_position_usd:
            raise ValueError(f"Pozisyon limiti: ${self.settings.max_position_usd}")

        with httpx.Client() as http:
            if pair.chain == "solana":
                result = swap_sol_to_token(
                    http, self._sol_rpc, self._sol_keypair,
                    pair.token_address, usd, self.settings.max_slippage_bps,
                )
                out_raw = result["out_amount"]
                cost = result["cost_usd"]
                dec = fetch_token_decimals(http, "solana", pair.token_address)
                amount_token = out_raw / (10**dec)
                sig = result["signature"][:8]
            else:
                result = evm_buy(
                    http, self._evm_web3[pair.chain], self._evm_account,
                    pair.chain, pair.token_address, usd,
                    self.settings.max_slippage_bps, self.settings.zero_x_api_key,
                )
                out_raw = result["buy_amount"]
                cost = result["sell_amount"] / 1_000_000
                amount_token = out_raw / (10 ** EVM_DECIMALS)
                sig = result["tx_hash"][:8]

        entry_price = cost / amount_token if amount_token else pair.price_usd
        pos = Position(
            pair_name=pair.name,
            chain=pair.chain,
            token_address=pair.token_address,
            pool_address=pair.pool_address,
            entry_price=entry_price,
            amount_token=amount_token,
            cost_usd=cost,
            opened_at=_now_iso(),
            entry_score=score,
            amount_raw=out_raw,
        )
        self.positions.append(pos)
        self._save()
        self._notify(f"🟢 ALIM [{pair.chain}] {pair.name} ${cost:.2f} tx={sig}...")
        return pos

    def sell(self, pos: Position, current_price: float, liquidity_usd: float, reason: str) -> Trade:
        with httpx.Client() as http:
            if pos.chain == "solana":
                dec = fetch_token_decimals(http, "solana", pos.token_address)
                amount_raw = pos.amount_raw or int(pos.amount_token * (10**dec))
                result = swap_token_to_sol(
                    http, self._sol_rpc, self._sol_keypair,
                    pos.token_address, amount_raw, self.settings.max_slippage_bps,
                )
                proceeds = result["proceeds_usd"]
                sig = result["signature"][:8]
            else:
                amount_raw = pos.amount_raw or int(pos.amount_token * (10 ** EVM_DECIMALS))
                result = evm_sell(
                    http, self._evm_web3[pos.chain], self._evm_account,
                    pos.chain, pos.token_address, amount_raw,
                    self.settings.max_slippage_bps, self.settings.zero_x_api_key,
                )
                proceeds = result["buy_amount"] / 1_000_000
                sig = result["tx_hash"][:8]

        exit_price = proceeds / pos.amount_token if pos.amount_token else current_price
        pnl = proceeds - pos.cost_usd
        trade = Trade(
            pair_name=pos.pair_name,
            chain=pos.chain,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            cost_usd=pos.cost_usd,
            proceeds_usd=proceeds,
            pnl_usd=pnl,
            opened_at=pos.opened_at,
            closed_at=_now_iso(),
            exit_reason=reason,
        )
        self.realized_pnl += pnl
        self.positions = [p for p in self.positions if p.pool_address != pos.pool_address]
        self._append_trade(trade)
        self._save()
        self._notify(f"🔴 SATIŞ [{pos.chain}] {pos.pair_name} {reason} PnL ${pnl:+.2f} tx={sig}...")
        return trade

    def sell_partial(
        self,
        pos: Position,
        fraction: float,
        current_price: float,
        liquidity_usd: float,
        reason: str,
    ) -> Trade:
        log.warning("Live partial sell — tam satış fallback (%.0f%%)", fraction * 100)
        return self.sell(pos, current_price, liquidity_usd, f"{reason} (live full)")

    @staticmethod
    def unrealized_pnl(pos: Position, current_price: float) -> float:
        return pos.amount_token * current_price - pos.cost_usd

    def summary(self) -> dict:
        wins = sum(1 for t in self.trades if t.pnl_usd > 0)
        total = len(self.trades)
        return {
            "balance": None,
            "live_chains": self.settings.live_chains(),
            "open_positions": len(self.positions),
            "realized_pnl": round(self.realized_pnl, 2),
            "trade_count": total,
            "win_rate": round(wins / total * 100, 1) if total else 0.0,
        }
