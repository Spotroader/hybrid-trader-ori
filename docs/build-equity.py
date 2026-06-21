#!/usr/bin/env python3
"""Equity grafigi veri derleyici (read-only).

Bu reponun data/trades.jsonl + data/paper_state.json dosyalarindan kasa-bakiyesi
serisini cikarir ve docs/equity-chart.html icindeki gomulu FALLBACK nesnesini
gunceller. Engine/bot dosyalarina YAZMAZ; yalniz docs/equity-chart.html'i gunceller.

Calistir:  python3 docs/build-equity.py
Sun:       cd docs && python3 -m http.server 8751   ->  http://localhost:8751/equity-chart.html

DATA = kronolojik [[ms, pnl], ...]  (ms = closed_at epoch ms, pnl = pnl_usd realized net)
BASE = paper_state.balance - sum(pnl_usd)
Tutarlilik: BASE + sum(pnl) == balance VE sum(pnl) ~= realized_pnl. Gecmezse HTML yazilmaz.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # docs/ -> repo koku
TRADES = ROOT / "data" / "trades.jsonl"
STATE = ROOT / "data" / "paper_state.json"
HTML = ROOT / "docs" / "equity-chart.html"

# Bu reponun kilometre taslari (varsa): {"label": "...", "ms": <epoch ms>}
EVENTS: list[dict] = []


def main() -> int:
    if not TRADES.exists() or not TRADES.read_text(encoding="utf-8").strip():
        print(f"trades bos/yok: {TRADES}. Once botu koştur (panel 8643), veri birikince tekrar calistir.")
        return 1

    rows: list[tuple[int, float]] = []
    for line in TRADES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
        ms = int(datetime.fromisoformat(t["closed_at"]).timestamp() * 1000)
        rows.append((ms, float(t["pnl_usd"])))
    rows.sort(key=lambda r: r[0])

    data = [[ms, pnl] for ms, pnl in rows]
    sum_pnl = sum(pnl for _, pnl in rows)

    state = json.loads(STATE.read_text(encoding="utf-8"))
    balance = float(state["balance"])
    realized_pnl = float(state.get("realized_pnl", 0.0))
    start_balance = float(state.get("start_balance", 0.0))
    base = balance - sum_pnl

    inv_ok = abs((base + sum_pnl) - balance) < 1e-6
    fields_ok = abs(sum_pnl - realized_pnl) < 0.01

    print(f"trade sayisi      : {len(rows)}")
    print(f"sum(pnl_usd)      : {sum_pnl:.6f}")
    print(f"paper realized_pnl: {realized_pnl:.6f}")
    print(f"paper balance     : {balance:.6f}")
    print(f"paper start_bal   : {start_balance:.6f}")
    print(f"BASE (hesap)      : {base:.6f}")
    print(f"BASE + cumsum son : {base + sum_pnl:.6f}  (balance'a esit mi: {inv_ok})")
    print(f"sum==realized     : {fields_ok}")

    if not (inv_ok and fields_ok):
        print("\nHATA: alan adlari/tutarlilik dogrulanamadi. HTML'e dokunulmadi.")
        return 2

    now = None
    if rows and not state.get("positions"):
        now = {
            "ms": rows[-1][0],
            "equity": round(balance, 2),
            "realized": round(sum_pnl, 2),
            "unrealized": 0.0,
            "cash": round(balance, 2),
            "deployed": 0,
        }

    fb = {"base": round(base, 6), "data": data, "events": EVENTS, "now": now}
    fb_json = json.dumps(fb, separators=(",", ":"))

    lines = HTML.read_text(encoding="utf-8").splitlines(keepends=True)
    replaced = 0
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("const FALLBACK ="):
            lines[i] = f"const FALLBACK = {fb_json};\n"
            replaced += 1
    if replaced != 1:
        print(f"HATA: FALLBACK satiri {replaced} kez bulundu (1 bekleniyordu). HTML'e dokunulmadi.")
        return 3
    HTML.write_text("".join(lines), encoding="utf-8")
    print(f"\nDOGRULANDI. {HTML.name} guncellendi (BASE={base:.2f}, {len(data)} nokta, {len(EVENTS)} kilometre tasi).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
