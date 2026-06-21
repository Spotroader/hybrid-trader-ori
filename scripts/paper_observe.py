#!/usr/bin/env python3
"""Paper mod gözlem günlüğü — watchlist + pozisyon snapshot (stdlib)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def fetch_state(base_url: str) -> dict:
    req = urllib.request.Request(f"{base_url.rstrip('/')}/api/state")
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def compact_snapshot(state: dict) -> dict:
    summary = state.get("summary") or {}
    watch = []
    for w in (state.get("watchlist") or [])[:15]:
        watch.append(
            {
                "name": w.get("name"),
                "score": w.get("score"),
                "chg_m5": w.get("chg_m5"),
                "chg_h1": w.get("chg_h1"),
                "chg_h24": w.get("chg_h24"),
                "turnover": w.get("turnover"),
                "liq_usd": w.get("liquidity_usd"),
                "pool": w.get("pool_address"),
            }
        )
    positions = []
    for p in state.get("positions") or []:
        positions.append(
            {
                "name": p.get("pair_name") or p.get("pair"),
                "entry": p.get("entry_price"),
                "current": p.get("current_price"),
                "pnl_usd": p.get("unrealized_pnl"),
                "pnl_pct": p.get("pnl_pct"),
                "cost_usd": p.get("cost_usd"),
                "pool": p.get("pool_address"),
            }
        )
    last = (state.get("decision") or {}).get("last")
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": state.get("mode"),
        "equity": summary.get("equity"),
        "balance": summary.get("balance"),
        "session_pnl": summary.get("session_pnl"),
        "open_positions": summary.get("open_positions"),
        "watchlist": watch,
        "positions": positions,
        "last_decision": last,
    }


def append_line(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_once(base_url: str, out: Path) -> dict:
    state = fetch_state(base_url)
    row = compact_snapshot(state)
    append_line(out, row)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper mod coin hareket gözlemi")
    parser.add_argument("--url", default="http://127.0.0.1:8642")
    parser.add_argument("--out", default="data/paper_observations.jsonl")
    parser.add_argument("--interval", type=int, default=0, help="Saniye; 0 = tek snapshot")
    parser.add_argument("--max", type=int, default=0, help="Max iterasyon; 0 = sınırsız")
    args = parser.parse_args()
    out = Path(args.out)

    n = 0
    while True:
        try:
            row = run_once(args.url, out)
            top = row["watchlist"][0]["name"] if row["watchlist"] else "—"
            print(
                f"[{row['ts'][:19]}] mode={row['mode']} equity=${row.get('equity')} "
                f"open={row.get('open_positions')} top={top}",
                flush=True,
            )
        except urllib.error.URLError as e:
            print(f"HATA: panel erişilemedi ({e})", file=sys.stderr, flush=True)
            if args.interval <= 0:
                return 1
        n += 1
        if args.interval <= 0 or (args.max > 0 and n >= args.max):
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
