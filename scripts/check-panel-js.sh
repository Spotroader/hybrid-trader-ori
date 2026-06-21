#!/bin/bash
# Panel JS syntax doğrulama — panel.py değişince çalıştır
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JS="$ROOT/src/hibrit_trader/static/panel.js"
if [[ ! -f "$JS" ]]; then
  echo "panel.js yok: $JS" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node yok — pytest tests/test_panel.py çalıştır" >&2
  exit 0
fi
node -e "const fs=require('fs'); new Function(fs.readFileSync('$JS','utf8')); console.log('panel.js OK')"
cd "$ROOT" && .venv/bin/python -m pytest tests/test_panel.py -q
