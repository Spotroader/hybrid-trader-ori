"""Alpha config — dosya + Helius key çözümleme."""

from pathlib import Path

from hibrit_trader.alpha_config import (
    alpha_config_status,
    load_alpha_wallet_addresses,
    resolve_helius_api_key,
)


def test_load_alpha_wallets_from_file():
    wallets = load_alpha_wallet_addresses()
    assert len(wallets) >= 10
    assert all(len(w) >= 32 for w in wallets)


def test_env_alpha_overrides_file(monkeypatch):
    monkeypatch.setenv("ALPHA_WALLETS", "Addr1,Addr2")
    assert load_alpha_wallet_addresses() == ["Addr1", "Addr2"]


def test_helius_from_rpc_url(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.setenv(
        "SOLANA_RPC_URL",
        "https://mainnet.helius-rpc.com/?api-key=test-helius-key",
    )
    assert resolve_helius_api_key() == "test-helius-key"


def test_alpha_config_status():
    st = alpha_config_status()
    assert st["alpha_wallets"] >= 10
    assert st["wallets_file_exists"] is True
    assert st["on_chain"] is True  # RPC fallback with wallet file
