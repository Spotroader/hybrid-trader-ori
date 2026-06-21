"""Alpha cüzdan listesi + Helius API key çözümleme."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def alpha_wallets_file_path() -> Path:
    raw = os.getenv("ALPHA_WALLETS_FILE", "config/alpha_wallets.txt")
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    return path


def load_alpha_wallet_addresses() -> list[str]:
    """ALPHA_WALLETS env öncelikli; yoksa ALPHA_WALLETS_FILE (varsayılan config/alpha_wallets.txt)."""
    from_env = [a.strip() for a in os.getenv("ALPHA_WALLETS", "").split(",") if a.strip()]
    if from_env:
        return from_env

    path = alpha_wallets_file_path()
    if not path.is_file():
        return []

    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        addr = line.split("#", 1)[0].strip().split()[0]
        if addr and addr not in seen:
            seen.add(addr)
            out.append(addr)
    return out


def _helius_key_from_rpc_url(rpc_url: str) -> str:
    if not rpc_url or "helius" not in rpc_url.lower():
        return ""
    parsed = urlparse(rpc_url)
    qs = parse_qs(parsed.query)
    for key in ("api-key", "api_key", "apiKey"):
        vals = qs.get(key)
        if vals and vals[0].strip():
            return vals[0].strip()
    return ""


def resolve_helius_api_key() -> str:
    """HELIUS_API_KEY → HELIUS_API_KEY_FILE → SOLANA_RPC_URL (?api-key=)."""
    direct = os.getenv("HELIUS_API_KEY", "").strip()
    if direct:
        return direct

    key_file = os.getenv("HELIUS_API_KEY_FILE", "").strip()
    if key_file:
        path = Path(key_file)
        if not path.is_absolute():
            path = project_root() / path
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.split("#", 1)[0].strip()

    local = project_root() / ".env.local"
    if local.is_file() and not direct:
        for line in local.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("HELIUS_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    return val

    return _helius_key_from_rpc_url(os.getenv("SOLANA_RPC_URL", ""))


def alpha_config_status() -> dict:
    wallets = load_alpha_wallet_addresses()
    key = bool(resolve_helius_api_key())
    path = alpha_wallets_file_path()
    rpc_fb = os.getenv("ALPHA_RPC_FALLBACK", "1") != "0"
    on_chain = (key and bool(wallets)) or (rpc_fb and bool(wallets))
    return {
        "helius": key,
        "alpha_wallets": len(wallets),
        "on_chain": on_chain,
        "rpc_fallback": rpc_fb and bool(wallets) and not key,
        "wallets_file": str(path),
        "wallets_file_exists": path.is_file(),
        "source": "env" if os.getenv("ALPHA_WALLETS", "").strip() else "file",
    }
