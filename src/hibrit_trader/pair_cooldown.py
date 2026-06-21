"""Pair cooldown — diskte kalıcı (motor restart sonrası churn önleme)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from hibrit_trader.cex_confluence import pair_base_symbol
from hibrit_trader.scanner import Pair


def _default_path() -> Path:
    raw = os.getenv("PAIR_COOLDOWN_FILE", "data/pair_cooldown.json")
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _cooldown_keys(token_address: str, pair_name: str) -> list[str]:
    sym = pair_name.split("/")[0].strip().upper() if "/" in pair_name else pair_name[:16].upper()
    return [f"token:{token_address}", f"sym:{sym}"]


class PairCooldownStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_path()
        self._until: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._until = {k: float(v) for k, v in (data.get("until") or {}).items()}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._until = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        active = {k: v for k, v in self._until.items() if v > now}
        self._until = active
        self.path.write_text(
            json.dumps({"until": active, "updated_at": now}, indent=0),
            encoding="utf-8",
        )

    def set_cooldown(self, token_address: str, pair_name: str, seconds: int) -> None:
        if seconds <= 0:
            return
        until = time.time() + seconds
        for key in _cooldown_keys(token_address, pair_name):
            self._until[key] = max(self._until.get(key, 0.0), until)
        self._save()

    def on_cooldown(self, token_address: str, pair_name: str) -> bool:
        now = time.time()
        return any(self._until.get(k, 0.0) > now for k in _cooldown_keys(token_address, pair_name))

    def on_cooldown_pair(self, pair: Pair) -> bool:
        return self.on_cooldown(pair.token_address, pair.name)

    def remaining_sec(self, token_address: str, pair_name: str) -> float:
        now = time.time()
        ends = [self._until.get(k, 0.0) for k in _cooldown_keys(token_address, pair_name)]
        best = max(ends) if ends else 0.0
        return max(0.0, best - now)
