"""EVM cüzdan bakiyeleri — public RPC, $0 API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from web3 import Web3

from hibrit_trader.evm_swap import EVM_CHAINS, USDC

CHAIN_LABELS = {"base": "Base", "arbitrum": "Arbitrum", "bsc": "BSC"}
NATIVE_SYMBOL = {"base": "ETH", "arbitrum": "ETH", "bsc": "BNB"}


# Bot işlem çiftleri için izlenen tokenlar (adres + decimals sabit)
WATCH_TOKENS: dict[str, list[dict]] = {
    "base": [
        {"symbol": "USDC", "address": USDC["base"], "decimals": 6},
        {"symbol": "WETH", "address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    ],
    "arbitrum": [
        {"symbol": "USDC", "address": USDC["arbitrum"], "decimals": 6},
        {"symbol": "USDT", "address": "0xFd086bC7CD5C481DCC9CE8855428A6F909824A97", "decimals": 6},
        {"symbol": "WETH", "address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
    ],
    "bsc": [
        {"symbol": "USDC", "address": USDC["bsc"], "decimals": 18},
        {"symbol": "USDT", "address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        {"symbol": "WBNB", "address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
    ],
}

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
]


@dataclass
class TokenBalance:
    symbol: str
    balance: float
    raw: int
    decimals: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "balance": self.balance,
            "decimals": self.decimals,
        }


def _fmt_amount(raw: int, decimals: int) -> float:
    return round(raw / (10**decimals), 6)


def fetch_chain_balances(rpc_url: str, address: str, chain: str) -> list[dict]:
    """Tek EVM ağında native + izlenen token bakiyeleri (sıfır olanlar hariç)."""
    if chain not in EVM_CHAINS:
        return []
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 12}))
    if not web3.is_connected():
        raise ConnectionError(f"RPC bağlantısı kurulamadı: {chain}")
    addr = Web3.to_checksum_address(address)
    out: list[TokenBalance] = []

    native_raw = web3.eth.get_balance(addr)
    if native_raw > 0:
        out.append(
            TokenBalance(
                symbol=NATIVE_SYMBOL[chain],
                balance=_fmt_amount(native_raw, 18),
                raw=native_raw,
                decimals=18,
            )
        )

    for tok in WATCH_TOKENS.get(chain, []):
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(tok["address"]),
            abi=ERC20_ABI,
        )
        raw = contract.functions.balanceOf(addr).call()
        if raw > 0:
            out.append(
                TokenBalance(
                    symbol=tok["symbol"],
                    balance=_fmt_amount(raw, tok["decimals"]),
                    raw=raw,
                    decimals=tok["decimals"],
                )
            )
    return [t.to_dict() for t in out]


def fetch_portfolio(rpc_map: dict[str, str], address: str) -> dict:
    """Tüm EVM ağlarında bakiye özeti."""
    addr = Web3.to_checksum_address(address)
    chains: dict[str, dict] = {}
    for chain in sorted(EVM_CHAINS):
        rpc = rpc_map.get(chain, "")
        entry: dict = {
            "chain": chain,
            "label": CHAIN_LABELS.get(chain, chain),
            "tokens": [],
            "error": None,
        }
        try:
            entry["tokens"] = fetch_chain_balances(rpc, addr, chain)
        except Exception as exc:  # noqa: BLE001 — panel read-only
            entry["error"] = str(exc)
        chains[chain] = entry
    return {"address": addr, "chains": chains}
