"""RugCheck — Solana token güvenlik özeti (GoPlus yedek / çift kontrol, Faz 8b)."""

from __future__ import annotations

import os
import time

import httpx

from hibrit_trader.safety import SafetyReport

RUGCHECK_BASE = "https://api.rugcheck.xyz"
MAX_SCORE_NORMALISED = 45.0
_LAST_CALL = 0.0


def rugcheck_enabled() -> bool:
    return os.getenv("RUGCHECK_ENABLED", "1") != "0"


def _rate_limit() -> None:
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    _LAST_CALL = time.time()


def summary_from_payload(data: dict) -> SafetyReport:
    """RugCheck summary JSON → SafetyReport."""
    reasons: list[str] = []
    for risk in data.get("risks") or []:
        level = str(risk.get("level") or "").lower()
        name = risk.get("name") or "risk"
        if level == "danger":
            reasons.append(f"RugCheck danger: {name}")
        elif level == "warn":
            val = risk.get("value")
            reasons.append(f"RugCheck warn: {name}" + (f" ({val})" if val else ""))

    score_norm = float(data.get("score_normalised") or 0)
    if score_norm > MAX_SCORE_NORMALISED:
        reasons.append(f"RugCheck skor yüksek ({score_norm:.0f}>{MAX_SCORE_NORMALISED:.0f})")

    # danger seviyesi varsa kesin RED; yalnız warn + yüksek skor da RED
    danger = any(str(r.get("level") or "").lower() == "danger" for r in (data.get("risks") or []))
    ok = not danger and score_norm <= MAX_SCORE_NORMALISED
    if not ok and not reasons:
        reasons.append("RugCheck RED")
    return SafetyReport(ok=ok, reasons=reasons, metrics={"rugcheck_score": round(score_norm, 1)})


def check_rugcheck_summary(client: httpx.Client, mint: str) -> SafetyReport:
    """GET /v1/tokens/{mint}/report/summary — ücretsiz, ~1 req/s."""
    _rate_limit()
    try:
        url = f"{RUGCHECK_BASE}/v1/tokens/{mint}/report/summary"
        resp = client.get(url, headers={"accept": "application/json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return SafetyReport(ok=False, reasons=["RugCheck verisi yok"])
        return summary_from_payload(data)
    except httpx.HTTPError as e:
        return SafetyReport(ok=False, reasons=[f"RugCheck erişilemedi: {type(e).__name__}"])
