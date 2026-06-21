from hibrit_trader.config import Settings


def test_live_chains_solana_only():
    s = Settings(mode="live", solana_private_key="abc", evm_private_key="", phantom_trading=False)
    assert s.live_chains() == ["solana"]


def test_live_chains_phantom_ignores_sol_key():
    s = Settings(mode="live", solana_private_key="abc", phantom_trading=True)
    assert s.live_chains() == []


def test_live_chains_evm_requires_0x_key():
    s = Settings(mode="live", evm_private_key="0xabc", zero_x_api_key="")
    assert s.live_chains() == []


def test_live_chains_both():
    s = Settings(
        mode="live",
        solana_private_key="sol",
        evm_private_key="0xevm",
        zero_x_api_key="0xkey",
        phantom_trading=False,
    )
    chains = s.live_chains()
    assert "solana" in chains
    assert "base" in chains
    assert "arbitrum" in chains
    assert "bsc" in chains
