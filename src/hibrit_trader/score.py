"""Fırsat skoru — 0..100. Deterministik, saf fonksiyon (test edilebilir).

Bileşenler:
- Hacim ivmesi: son 5dk hacmi saatlik ortalamaya göre ne kadar hızlandı (w=30)
- Hacim trendi: son 1s hacmi 24s ortalamasına göre (w=20)
- Fiyat momentumu: h1 değişim — ılımlı yükseliş ideal, aşırısı pump riski (w=20)
- Likidite derinliği: 30k..1M USD log ölçek (w=20)
- İşlem yoğunluğu: h1 işlem sayısı (w=10)
- Gas cezası: swap maliyeti / max pozisyon oranı kadar düşülür
"""

from __future__ import annotations

import math
import os

from hibrit_trader.config import GAS_COST_USD
from hibrit_trader.scanner import Pair

MIN_LIQUIDITY_USD = 30_000.0


def _min_liq_for_pair(p: Pair) -> float:
    import os

    boost = int(getattr(p, "boost_score", 0) or 0)
    if boost >= 50:
        return float(os.getenv("TRENDING_MIN_LIQ_USD", "12000"))
    return float(os.getenv("MIN_LIQUIDITY_SCORE_USD", str(MIN_LIQUIDITY_USD)))


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _price_momentum_score(p: Pair) -> float:
    """h1/m5 momentum — negatif h1 tam sıfır değil; pump cezası yumuşak (Faz 8)."""
    if p.chg_h1 <= 0:
        if p.chg_m5 > 0:
            return min(p.chg_m5 / 10, 0.25)
        return 0.08
    if p.chg_h1 <= 20:
        return p.chg_h1 / 20
    # %20–80 arası kademeli düşüş (eski: sert cliff)
    return _clip(1.0 - (p.chg_h1 - 20) / 80, 0.35, 1.0)


def opportunity_score(
    p: Pair,
    max_position_usd: float = 20.0,
    *,
    cex_boost: float = 0.0,
) -> float:
    """0..100 skor. Likidite tabanın altındaysa veya çift hareketsizse 0."""
    min_liq = _min_liq_for_pair(p)
    if p.liquidity_usd < min_liq or p.price_usd <= 0:
        return 0.0
    if abs(p.chg_h1) < 0.5 and abs(p.chg_h24) < 2.0:
        return 0.0

    momentum = _clip((p.vol_m5 * 12) / max(p.vol_h1, 1.0), 0, 3) / 3
    trend = _clip((p.vol_h1 * 24) / max(p.vol_h24, 1.0), 0, 3) / 3
    price = _price_momentum_score(p)

    liq = _clip(math.log10(p.liquidity_usd / min_liq) / math.log10(1_000_000 / min_liq), 0, 1)
    activity = _clip(p.txns_h1 / 300, 0, 1)

    raw = 30 * momentum + 20 * trend + 20 * price + 20 * liq + 10 * activity

    gas_penalty = 100 * (2 * GAS_COST_USD.get(p.chain, 0.1)) / max_position_usd
    boosted = _clip(raw - gas_penalty + cex_boost, 0, 100)
    return round(boosted, 1)


def rank(
    pairs: list,
    max_position_usd: float = 20.0,
    *,
    cex_scores: dict[str, float] | None = None,
    client=None,
) -> list:
    """(skor, Pair) listesi — yüksekten düşüğe, 0 skorlular elenmiş."""
    from hibrit_trader.cex_confluence import cex_boost_points
    from hibrit_trader.dex_boost import dex_boost_entry_adjustment
    from hibrit_trader.dex_trending_strategy import trending_score
    from hibrit_trader.early_launch import genesis_score
    from hibrit_trader.pump_research import analyze_pump_pair
    from hibrit_trader.smart_money import _proxy_wallet_buyers

    scored: list[tuple[float, Pair]] = []
    for p in pairs:
        boost, _ = cex_boost_points(p, cex_scores)
        bs = int(getattr(p, "boost_score", 0) or 0)
        ds_boost = dex_boost_entry_adjustment(bs)
        s = opportunity_score(p, max_position_usd, cex_boost=boost + ds_boost)
        ts = trending_score(p)
        if bs > 0 or ts >= 50:
            s = round(max(s, s * 0.35 + ts * 0.65), 1)
        # Skor sıralaması: proxy cüzdan (tick başına N×12 RPC alpha yapma)
        wallets = _proxy_wallet_buyers(p)
        moon = analyze_pump_pair(p, wallet_count=wallets).moonshot_score
        if moon >= 62:
            s = round(min(100.0, s + min(10.0, (moon - 58) * 0.35)), 1)
        gen = genesis_score(p)
        if gen >= float(os.getenv("GENESIS_POOL_MIN", "40")):
            s = round(min(100.0, max(s, gen)), 1)
        from hibrit_trader.early_launch import pump_entry_ok, runner_entry_ok

        early_ok, _ = pump_entry_ok(p)
        if early_ok:
            rok, _ = runner_entry_ok(p)
            if rok:
                rs = min(100.0, p.chg_h1 * 1.6 + p.chg_m5 * 2.2 + s * 0.25)
                s = round(min(100.0, max(s, rs)), 1)
        if s > 0 or gen >= float(os.getenv("GENESIS_ENTRY_MIN", "52")) or early_ok:
            if s <= 0:
                s = round(gen, 1)
            scored.append((s, p))
    return sorted(scored, key=lambda sp: sp[0], reverse=True)
