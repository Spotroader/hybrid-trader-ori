# hibrit-trader

On-chain fırsat avcısı: çok ağlı DEX botu. Tarayıcı → güvenlik filtresi → fırsat skoru → oturum (gir/çık) → aggregator yürütme.

- **Ağlar:** Solana (öncelik) + Base / Arbitrum + BSC — ETH ana ağ **yok** (gas)
- **Yürütme:** Jupiter (Solana), 1inch/0x (EVM) — en ucuz DEX rotasını aggregator seçer
- **Veri:** DexScreener + GeckoTerminal (ücretsiz, key'siz)
- **Güvenlik filtresi:** GoPlus + honeypot + likidite/holder kontrolü — geçmeyen coin'e işlem yok
- **Mod:** `paper` (varsayılan, sanal dolum) ↔ `live`
- **Panel:** FastAPI web — işlem geçmişi, PnL, açık pozisyon, fırsat listesi
- **API bütçesi:** $0 — tamamı ücretsiz katman

## Güvenlik ilkeleri (pazarlıksız)

1. Ana MetaMask/cüzdan seed'i **asla** bota girmez → [docs/cuzdan-kurulum.md](docs/cuzdan-kurulum.md)
2. Güvenlik filtresinden geçmeyen coin'e işlem yok
3. Sıkı slippage limiti, işlem başına max pozisyon, günlük zarar limiti + kill-switch
4. Canlı ilk sermaye: $50–100

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # sonra docs/cuzdan-kurulum.md'yi izle
```

## Çalıştırma

```bash
python -m hibrit_trader          # config durumu
python -m hibrit_trader scan     # fırsat taraması (işlemsiz)
python -m hibrit_trader run      # paper/live motor + panel → http://127.0.0.1:8642
pytest                           # doğrulama
```

**Canlı mod:** `.env` → `BOT_MODE=live` + en az bir key:
- Solana: `SOLANA_PRIVATE_KEY` (Jupiter)
- EVM (Base/Arbitrum/BSC): `EVM_PRIVATE_KEY` + `ZEROX_API_KEY` (ücretsiz: [0x.org](https://0x.org))

Bot en yüksek skorlu fırsatı **key'in olan ağda** işleme alır. Ağlar arası bridge otomatik değil — her ağda ayrı USDC gerekir.

## Fazlar

| Faz | Kapsam | Durum |
|-----|--------|-------|
| 0 | İskelet + cüzdan + ücretsiz RPC | ✅ |
| 1 | Tarayıcı + güvenlik filtresi + fırsat skoru | ✅ |
| 2 | Paper motor + FastAPI panel + oturum mantığı | ✅ |
| 3 | Solana canlı (Jupiter) + kill-switch + Telegram | ✅ |
| 4 | Base/Arbitrum/BSC (0x API) + çok ağlı yönlendirme | ✅ |

Plan: `~/.cursor/plans/hibrit_bot_olabilirlik_planı_c8ec77b7.plan.md` · Wiki: `~/Desktop/yz/wiki/wiki/projects/hibrit-trader.md`
