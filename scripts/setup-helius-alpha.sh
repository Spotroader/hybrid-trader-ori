#!/usr/bin/env bash
# Helius API key → .env.local (gitignore). Alpha cüzdanlar config/alpha_wallets.txt'ten yüklenir.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$ROOT/.env.local"
KEY="${1:-}"

if [ -z "$KEY" ]; then
  echo "Kullanım: $0 <HELIUS_API_KEY>"
  echo "Not: Helius artık ücretli plan — paper için ALPHA_RPC_FALLBACK=1 yeterli (\$0)"
  echo ""
  echo "Alpha cüzdanlar: $ROOT/config/alpha_wallets.txt ($(grep -cve '^\s*#' "$ROOT/config/alpha_wallets.txt" 2>/dev/null || echo 0) adres)"
  exit 1
fi

tmp="$(mktemp)"
if [ -f "$LOCAL" ]; then
  grep -v '^HELIUS_API_KEY=' "$LOCAL" > "$tmp" || true
else
  : > "$tmp"
fi
echo "HELIUS_API_KEY=$KEY" >> "$tmp"
mv "$tmp" "$LOCAL"
chmod 600 "$LOCAL" 2>/dev/null || true
echo "✓ $LOCAL yazıldı"
echo "  Alpha: config/alpha_wallets.txt"
echo "  Doğrula: cd $ROOT && .venv/bin/python -m hibrit_trader status"
echo "  Motor restart: kill \$(lsof -t -iTCP:8642) 2>/dev/null; .venv/bin/python -m hibrit_trader run"
