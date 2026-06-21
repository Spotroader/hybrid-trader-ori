# Adanmış bot cüzdanı kurulumu

**Altın kural: Ana cüzdanının seed phrase'i (12/24 kelime) hiçbir zaman bota, `.env`'e veya bu bilgisayardaki bir dosyaya girmez.** Bot, sadece içinde küçük bakiye olan adanmış bir hesabın private key'ini kullanır. En kötü senaryoda (key sızar) kaybın o hesaptaki tutarla sınırlı kalır.

## 1. EVM bot hesabı (Base / Arbitrum / BSC) — MetaMask

1. MetaMask → sağ üst hesap menüsü → **Hesap ekle** → yeni hesap oluştur (adı: `bot`).
2. Bu yeni hesabı seç → **⋮ → Hesap ayrıntıları → Private key'i göster** → şifreni gir, key'i kopyala.
3. `.env` dosyasına yapıştır: `EVM_PRIVATE_KEY=0x...`
4. Ana hesabından bu `bot` hesabına **küçük tutar** gönder (başlangıç: $50–100 + az miktar gas için ETH/BNB).
5. Ana hesabının adresini (key DEĞİL) izleme için ekle: `WATCH_EVM_ADDRESS=0x...`

> MetaMask'te aynı seed altındaki yeni hesabın key'i ayrıdır — bot key'i sızsa bile seed ve diğer hesaplar etkilenmez. Yine de bot hesabında asla büyük bakiye tutma.

## 2. Solana — Phantom panel (önerilen, key yok)

1. Chrome/Brave'de panel aç: `http://127.0.0.1:8642`
2. **Phantom** butonuna tıkla → cüzdanı bağla
3. Cüzdanda **SOL** bulundur (USDC gerekmez) — bot **SOL paritesi** ile alım/satım yapar
4. `.env`: `PHANTOM_TRADING=1` (varsayılan) — `SOLANA_PRIVATE_KEY` **boş bırak**
5. Paper modda bakiye otomatik senkron; canlı modda her swap Phantom onayı ister

Gas rezervi: ~0.05 SOL işlem ücreti için ayrılır; kalan SOL alım gücüne yazılır.

### Legacy: sunucu key (PHANTOM_TRADING=0)

Eski akış — private key export → `.env` `SOLANA_PRIVATE_KEY=...` — yalnız adanmış bot cüzdanı için.

## 3. RPC (ücretsiz — Helius artık ücretli plan)

Boş bırakırsan bot **public Solana RPC** kullanır (yavaş, rate limit). Daha iyi limit için ücretsiz kayıt:

| Ağ | Sağlayıcı | Not |
|----|-----------|-----|
| Solana | [QuickNode](https://www.quicknode.com/chains/sol) | Free trial / düşük limit |
| Solana | [Chainstack](https://chainstack.com) | Free developer tier |
| Solana | PublicNode / Ankr | URL doğrudan `.env` — kayıt opsiyonel |
| Base / Arbitrum | [alchemy.com](https://alchemy.com) | 300M CU/ay free |

`.env` örneği:

```env
SOLANA_RPC_URL=https://solana-rpc.publicnode.com
# yedek (virgülle):
SOLANA_RPC_FALLBACK_URLS=https://api.mainnet-beta.solana.com,https://rpc.ankr.com/solana
ALPHA_RPC_FALLBACK=1
ALPHA_WALLET_SCAN_LIMIT=5
```

## 3b. Alpha cüzdan takibi (12 KOL — $0 varsayılan)

**Helius free kaldırıldı** (2026 — yalnız ücretli plan). Paper/canlı başlangıç için **ücretsiz yol:**

1. **`config/alpha_wallets.txt`** — 12 KOL (git'te, düzenlenebilir)
2. **`ALPHA_RPC_FALLBACK=1`** (varsayılan) — public Solana RPC ile swap sayımı
3. **Proxy 🐋** — txns/hacim heuristic (API key yok)

Ücretli Helius (Enhanced TX, hızlı) — yalnız bilinçli opt-in:

```bash
bash scripts/setup-helius-alpha.sh YOUR_PAID_HELIUS_KEY
```

Panel **Cüzdan** sütunu: **⛓ rpc** = public RPC alpha · **~** = proxy · **⛓ helius** = ücretli API

Kaynak: community KOL listeleri — `config/alpha_wallets.txt` güncelle.

## 4. Kontrol listesi

- [ ] `.env` oluşturuldu (`cp .env.example .env`) ve **git'e girmiyor** (`.gitignore`'da)
- [ ] Bot hesapları adanmış — ana seed hiçbir yere yazılmadı
- [ ] Bot hesaplarında sadece küçük bakiye var
- [ ] `BOT_MODE=paper` (canlıya geçiş Faz 3'te, ayrıca konuşulacak)
- [ ] `python -m hibrit_trader` çalıştırıldı, "Config hazır" görüldü
