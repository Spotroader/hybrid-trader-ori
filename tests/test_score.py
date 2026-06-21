from dataclasses import replace

from hibrit_trader.scanner import Pair
from hibrit_trader.score import MIN_LIQUIDITY_USD, opportunity_score, rank


def _pair(**kw) -> Pair:
    temel = dict(
        chain="solana", dex="raydium", pool_address="P", token_address="T",
        name="X / SOL", price_usd=1.0, liquidity_usd=200_000,
        vol_m5=5000, vol_h1=50_000, vol_h24=600_000,
        chg_m5=1.0, chg_h1=8.0, chg_h24=15.0, txns_h1=150,
    )
    temel.update(kw)
    return Pair(**temel)


def test_dusuk_likidite_sifir():
    assert opportunity_score(_pair(liquidity_usd=MIN_LIQUIDITY_USD - 1)) == 0.0


def test_hareketsiz_cift_sifir():
    # Stable/blue-chip havuzu: yüksek likidite ama fiyat hareketi yok → fırsat değil
    assert opportunity_score(_pair(liquidity_usd=10_000_000, chg_h1=0.1, chg_h24=0.3)) == 0.0


def test_skor_araliktadir():
    s = opportunity_score(_pair())
    assert 0 < s <= 100


def test_hacim_ivmesi_skoru_artirir():
    yavas = opportunity_score(_pair(vol_m5=1000))
    hizli = opportunity_score(_pair(vol_m5=20_000))
    assert hizli > yavas


def test_asiri_pump_cezalandirilir():
    ilimli = opportunity_score(_pair(chg_h1=10))
    asiri = opportunity_score(_pair(chg_h1=90))
    assert ilimli > asiri


def test_ucuz_ag_avantajli():
    sol = opportunity_score(_pair(chain="solana"))
    bsc = opportunity_score(_pair(chain="bsc"))
    assert sol > bsc


def test_rank_sirali_ve_sifirsiz():
    pairs = [_pair(), _pair(liquidity_usd=0), _pair(vol_m5=20_000)]
    sirali = rank(pairs)
    assert len(sirali) == 2
    assert sirali[0][0] >= sirali[1][0]
