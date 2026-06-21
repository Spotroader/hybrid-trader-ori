"""GoPlus güvenlik filtresi — geçmeyen coin'e işlem YOK (pazarlıksız kural).

EVM: token_security/{chain_id} · Solana: solana/token_security — ikisi de ücretsiz.
Solana: RugCheck yedek / çift kontrol (Faz 8b).
API erişilemezse karar 'belirsiz' değil 'RED' — güvenlik filtresi fail-closed çalışır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from hibrit_trader.config import API, GOPLUS_EVM_CHAIN_ID

MAX_TAX_PCT = 10.0


def _max_top10_holder_pct() -> float:
    """Paper agresif modda meme havuzları için daha yüksek tavan (bilinçli risk)."""
    if os.getenv("MAX_TOP10_HOLDER_PCT"):
        return float(os.getenv("MAX_TOP10_HOLDER_PCT", "70"))
    if os.getenv("BOT_MODE", "paper").lower() == "paper" and os.getenv("PAPER_AGGRESSIVE", "1") != "0":
        return 92.0
    return 70.0


@dataclass
class SafetyReport:
    ok: bool
    reasons: list = field(default_factory=list)  # RED nedenleri (boş = temiz)


def _goplus_no_data(report: SafetyReport) -> bool:
    if not report.reasons:
        return False
    msg = report.reasons[0].lower()
    return "verisi yok" in msg or "erişilemedi" in msg


def entry_safety_ok(report: SafetyReport, *, genesis_ok: bool = False) -> tuple[bool, str]:
    """Giriş güvenliği — paper genesis: index yok/warn kabul, danger/honeypot asla."""
    if report.ok:
        return True, "OK"
    if not genesis_ok or os.getenv("BOT_MODE", "paper").lower() != "paper":
        return False, "; ".join(report.reasons[:2])
    if os.getenv("GENESIS_SAFETY_LAX", "1") == "0":
        return False, "; ".join(report.reasons[:2])
    blob = " ".join(report.reasons).lower()
    hard = (
        "honeypot",
        "rugcheck danger",
        "satış engelli",
        "mint yetkisi açık",
        "freeze yetkisi açık",
        "transfer hook",
    )
    if any(h in blob for h in hard):
        return False, "; ".join(report.reasons[:2])
    if _goplus_no_data(report) or "rugcheck verisi yok" in blob or "rugcheck erişilemedi" in blob:
        return True, "genesis paper · index yok"
    if report.reasons and all(
        "warn" in r.lower() or "skor" in r.lower() for r in report.reasons
    ):
        return True, "genesis paper · warn kabul"
    return False, "; ".join(report.reasons[:2])


def _merge_solana_safety(goplus: SafetyReport, rugcheck: SafetyReport) -> SafetyReport:
    if not goplus.ok and _goplus_no_data(goplus):
        return rugcheck
    if not goplus.ok:
        return goplus
    if os.getenv("RUGCHECK_STRICT", "1") == "0":
        return goplus
    if not rugcheck.ok:
        return SafetyReport(ok=False, reasons=list(rugcheck.reasons))
    return goplus


def _evm_decision(d: dict) -> SafetyReport:
    """GoPlus EVM token_security yanıtından karar üretir."""
    reasons = []
    if d.get("is_honeypot") == "1":
        reasons.append("honeypot")
    if d.get("cannot_sell_all") == "1":
        reasons.append("satış engelli")
    if float(d.get("buy_tax") or 0) * 100 > MAX_TAX_PCT:
        reasons.append(f"alım vergisi >%{MAX_TAX_PCT:.0f}")
    if float(d.get("sell_tax") or 0) * 100 > MAX_TAX_PCT:
        reasons.append(f"satış vergisi >%{MAX_TAX_PCT:.0f}")
    if d.get("is_open_source") == "0":
        reasons.append("kontrat kapalı kaynak")
    if d.get("hidden_owner") == "1":
        reasons.append("gizli owner")
    if d.get("owner_change_balance") == "1":
        reasons.append("owner bakiye değiştirebilir")
    if d.get("is_mintable") == "1":
        reasons.append("mint edilebilir")
    holders = d.get("holders") or []
    top10 = sum(float(h.get("percent") or 0) for h in holders[:10]) * 100
    cap = _max_top10_holder_pct()
    if top10 > cap:
        reasons.append(f"top10 holder %{top10:.0f}")
    return SafetyReport(ok=not reasons, reasons=reasons)


def _solana_decision(d: dict) -> SafetyReport:
    """GoPlus Solana token_security yanıtından karar üretir."""
    reasons = []
    if (d.get("mintable") or {}).get("status") == "1":
        reasons.append("mint yetkisi açık")
    if (d.get("freezable") or {}).get("status") == "1":
        reasons.append("freeze yetkisi açık")
    if (d.get("transfer_fee_upgradable") or {}).get("status") == "1":
        reasons.append("transfer ücreti değiştirilebilir")
    if d.get("transfer_hook") not in (None, [], ""):
        reasons.append("transfer hook var")
    holders = d.get("holders") or []
    top10 = sum(float(h.get("percent") or 0) for h in holders[:10])
    cap = _max_top10_holder_pct()
    if top10 > cap:
        reasons.append(f"top10 holder %{top10:.0f}")
    return SafetyReport(ok=not reasons, reasons=reasons)


def _check_goplus(client: httpx.Client, chain: str, token_address: str) -> SafetyReport:
    try:
        if chain == "solana":
            url = f"{API['goplus']}/solana/token_security"
            resp = client.get(url, params={"contract_addresses": token_address}, timeout=15)
            resp.raise_for_status()
            data = (resp.json().get("result") or {}).get(token_address)
            if not data:
                return SafetyReport(ok=False, reasons=["GoPlus verisi yok"])
            return _solana_decision(data)

        chain_id = GOPLUS_EVM_CHAIN_ID.get(chain)
        if not chain_id:
            return SafetyReport(ok=False, reasons=[f"desteklenmeyen ağ: {chain}"])
        url = f"{API['goplus']}/token_security/{chain_id}"
        resp = client.get(url, params={"contract_addresses": token_address}, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        data = result.get(token_address.lower()) or result.get(token_address)
        if not data:
            return SafetyReport(ok=False, reasons=["GoPlus verisi yok"])
        return _evm_decision(data)
    except httpx.HTTPError as e:
        return SafetyReport(ok=False, reasons=[f"GoPlus erişilemedi: {type(e).__name__}"])


def check_token(
    client: httpx.Client,
    chain: str,
    token_address: str,
    *,
    genesis_ok: bool = False,
) -> SafetyReport:
    """Tek token güvenlik kararı. Veri yoksa/erişim hatasında RED (fail-closed)."""
    report = _check_goplus(client, chain, token_address)
    if chain != "solana":
        return report
    from hibrit_trader.rugcheck import check_rugcheck_summary, rugcheck_enabled

    if rugcheck_enabled():
        rug = check_rugcheck_summary(client, token_address)
        report = _merge_solana_safety(report, rug)

    from hibrit_trader.holder_risk import check_holder_concentration, holder_risk_enabled

    if holder_risk_enabled():
        holder = check_holder_concentration(client, token_address, genesis_ok=genesis_ok)
        if not holder.ok and holder.reasons and not holder.reasons[0].startswith("holder risk skip"):
            return SafetyReport(ok=False, reasons=list(holder.reasons))
    return report
