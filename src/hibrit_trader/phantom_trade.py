"""Phantom imza kuyruğu — canlı Jupiter swap'ları tarayıcıda imzalanır."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


class PhantomPendingTrade(Exception):
    """Broker alım/satımı kuyruğa aldı; panel imzalamalı."""

    def __init__(self, trade_id: str) -> None:
        self.trade_id = trade_id
        super().__init__(trade_id)


@dataclass
class PendingTrade:
    id: str
    kind: str
    tx_b64: str
    meta: dict[str, Any] = field(default_factory=dict)


class PhantomTradeQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingTrade] = {}

    def enqueue(self, kind: str, tx_b64: str, meta: dict[str, Any]) -> str:
        trade_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._pending[trade_id] = PendingTrade(trade_id, kind, tx_b64, dict(meta))
        return trade_id

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": p.id,
                    "kind": p.kind,
                    "tx_base64": p.tx_b64,
                    "pair": p.meta.get("pair_name"),
                    "chain": p.meta.get("chain", "solana"),
                    "usd": p.meta.get("usd"),
                    "reason": p.meta.get("reason"),
                }
                for p in self._pending.values()
            ]

    def take(self, trade_id: str) -> PendingTrade | None:
        with self._lock:
            return self._pending.pop(trade_id, None)


phantom_queue = PhantomTradeQueue()
