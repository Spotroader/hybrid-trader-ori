"""Saito beyin — sinyal toplama, karşı taraf tahmini, rejim + aksiyon önerisi."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from hibrit_trader.advanced_scan.runner import run_advanced_scan
from hibrit_trader.brain.adversary import predict_counterparty
from hibrit_trader.brain.intel import fetch_fear_greed


@dataclass
class BrainVerdict:
    regime: str  # risk_on | neutral | risk_off
    action_bias: str  # aggressive | neutral | defensive
    entry_penalty: float  # decision.py giriş eşiğine eklenir
    exit_bias: str  # aggressive | neutral | defensive — ExitPolicy ayarı
    counterparty_thesis: str
    predicted_moves: list[dict]
    confidence: float
    macro_avg: float | None
    fear_greed: int | None
    fear_greed_label: str | None
    scan_count: int
    tam_isabet_symbols: list[str]
    top_picks: list[dict]
    sources: list[str]
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "action_bias": self.action_bias,
            "entry_penalty": self.entry_penalty,
            "exit_bias": self.exit_bias,
            "counterparty_thesis": self.counterparty_thesis,
            "predicted_moves": self.predicted_moves,
            "confidence": self.confidence,
            "macro_avg": self.macro_avg,
            "fear_greed": self.fear_greed,
            "fear_greed_label": self.fear_greed_label,
            "scan_count": self.scan_count,
            "tam_isabet_symbols": self.tam_isabet_symbols,
            "top_picks": self.top_picks,
            "sources": self.sources,
            "updated_at": self.updated_at,
        }


def _macro_from_scan(results: list[dict]) -> float | None:
    majors = [r["score"] for r in results if r.get("symbol") in ("BTC", "ETH", "SOL")]
    if not majors:
        return None
    return round(sum(majors) / len(majors), 1)


def _regime_and_bias(
    macro_avg: float | None,
    fear_greed: int | None,
    adversary_summary: str,
    trap_heavy: bool,
) -> tuple[str, str, float]:
    penalty = 0.0
    if trap_heavy:
        return "risk_off", "defensive", 12.0
    if macro_avg is not None and macro_avg < 38:
        penalty += 10.0
    if fear_greed is not None and fear_greed >= 80:
        penalty += 8.0
    elif fear_greed is not None and fear_greed <= 20:
        penalty -= 3.0

    if penalty >= 10:
        return "risk_off", "defensive", penalty
    if penalty <= 0 and macro_avg is not None and macro_avg >= 55:
        return "risk_on", "aggressive", max(penalty, -3.0)
    return "neutral", "neutral", penalty


def run_brain(
    modes: list[str] | None = None,
    limit: int = 15,
) -> BrainVerdict:
    """Tek döngü: gelişmiş tarama + intel + karşı taraf → verdict."""
    active = modes or ["cex", "news", "whale", "derivatives"]
    scan = run_advanced_scan(active, limit=limit)
    results = scan.get("results", [])

    fg = fetch_fear_greed()
    fg_val = fg["value"] if fg else None
    macro_avg = _macro_from_scan(results)

    adversary = predict_counterparty(
        macro_avg=macro_avg,
        fear_greed=fg_val,
        top_scan=results,
    )
    trap_heavy = adversary.dominant_trap in ("likidasyon avı / bull trap",)

    regime, bias, penalty = _regime_and_bias(
        macro_avg, fg_val, adversary.summary, trap_heavy
    )

    tam = [r["symbol"] for r in results if r.get("tam_isabet")]
    confidence = min(
        95.0,
        40.0
        + len(results) * 2
        + len(adversary.moves) * 5
        + (10 if macro_avg is not None else 0)
        + (10 if fg_val is not None else 0),
    )

    sources = ["advanced_scan", "binance_futures", "cryptocurrency.cv"]
    if fg:
        sources.append("alternative.me/fng")

    thesis = adversary.summary
    if tam:
        thesis += f" Tam isabet: {', '.join(tam[:5])}."

    return BrainVerdict(
        regime=regime,
        action_bias=bias,
        entry_penalty=penalty,
        exit_bias=bias,
        counterparty_thesis=thesis,
        predicted_moves=[
            {
                "actor": m.actor,
                "action": m.likely_action,
                "impact": m.impact,
                "confidence": m.confidence,
            }
            for m in adversary.moves
        ],
        confidence=round(confidence, 1),
        macro_avg=macro_avg,
        fear_greed=fg_val,
        fear_greed_label=fg.get("label") if fg else None,
        scan_count=len(results),
        tam_isabet_symbols=tam,
        top_picks=results[:5],
        sources=sources,
    )
