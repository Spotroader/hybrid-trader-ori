"""Karşı taraf (MM, balina, kalabalık long/short) hamle tahmini — kural tabanlı."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CounterpartyMove:
    actor: str
    likely_action: str
    impact: str  # bullish | bearish | trap
    confidence: float  # 0..100


@dataclass
class AdversaryReport:
    moves: list[CounterpartyMove] = field(default_factory=list)
    dominant_trap: str | None = None
    summary: str = ""


def predict_counterparty(
    *,
    macro_avg: float | None,
    fear_greed: int | None,
    top_scan: list[dict],
) -> AdversaryReport:
    """Funding/OI/haber/makro birleşiminden karşı taraf senaryoları."""
    moves: list[CounterpartyMove] = []

    if macro_avg is not None and macro_avg < 40:
        moves.append(
            CounterpartyMove(
                "Akıllı para (CEX)",
                "Zayıf trendde likidite avı — stop-loss kümelerini süpürme",
                "trap",
                65.0,
            )
        )

    if fear_greed is not None and fear_greed >= 75:
        moves.append(
            CounterpartyMove(
                "Perakende kalabalık",
                "FOMO ile long şişirme; MM funding toplama",
                "bearish",
                60.0,
            )
        )
    elif fear_greed is not None and fear_greed <= 25:
        moves.append(
            CounterpartyMove(
                "Balina / MM",
                "Korkuda spot/OTC birikim; kısa vadeli short squeeze kurulumu",
                "bullish",
                55.0,
            )
        )

    for row in top_scan[:5]:
        sym = row.get("symbol", "?")
        deriv = row.get("deriv_score")
        fr_note = row.get("reason", "")
        if deriv is not None and deriv < 35:
            moves.append(
                CounterpartyMove(
                    f"Binance MM ({sym})",
                    "Aşırı pozitif funding + OI → long likidasyon avı",
                    "trap",
                    70.0,
                )
            )
        if "squeeze" in fr_note.lower() or (row.get("deriv_score") or 0) > 65:
            moves.append(
                CounterpartyMove(
                    f"Türev piyasa ({sym})",
                    "Short squeeze — zorla kapanış dalgası",
                    "bullish",
                    58.0,
                )
            )
        if row.get("tam_isabet"):
            moves.append(
                CounterpartyMove(
                    f"Erken narrative ({sym})",
                    "Influencer/bot pump sonrası dağıtım (rug window)",
                    "trap",
                    62.0,
                )
            )

    trap_count = sum(1 for m in moves if m.impact == "trap")
    bull = sum(1 for m in moves if m.impact == "bullish")
    bear = sum(1 for m in moves if m.impact == "bearish")

    if trap_count >= 2:
        dominant = "likidasyon avı / bull trap"
        summary = "Karşı taraf muhtemelen long tarafı süpürmeye veya pump sonrası satışa hazırlanıyor — agresif giriş cezalı."
    elif bull > bear + 1:
        dominant = "squeeze / birikim"
        summary = "Karşı taraf kısa pozisyonu zorlamaya veya dip toplamaya meyilli — seçici long."
    elif bear > bull + 1:
        dominant = "dağıtım"
        summary = "Karşı taraf yükselişi satışa çevirebilir — savunmacı mod."
    else:
        dominant = None
        summary = "Net baskın hamle yok — mevcut kural tabanlı eşikler geçerli."

    return AdversaryReport(moves=moves[:8], dominant_trap=dominant, summary=summary)
