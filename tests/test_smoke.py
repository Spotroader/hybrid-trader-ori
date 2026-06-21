"""Kritik invariant'lar — CI/regresyon duman testi."""

from __future__ import annotations

from hibrit_trader.config import Settings
from hibrit_trader.exit_policy import ExitPolicy
from hibrit_trader.pair_cooldown import PairCooldownStore
from hibrit_trader.safety import SafetyReport, _merge_solana_safety


def test_exit_policy_founder_scratch_relaxed():
    base = ExitPolicy()
    ep = ExitPolicy.for_dex_trending(base)
    assert ep.scratch_pct <= -5.0


def test_pair_cooldown_isolated(tmp_path):
    store = PairCooldownStore(path=tmp_path / "cd.json")
    store.set_cooldown("tok-A", "AAA / SOL", 3600)
    assert store.on_cooldown("tok-A", "AAA / SOL")
    assert not store.on_cooldown("tok-B", "BBB / SOL")


def test_rugcheck_strict_blocks():
    goplus = SafetyReport(ok=True, reasons=[])
    rug = SafetyReport(ok=False, reasons=["RugCheck skor yüksek (80>45)"])
    merged = _merge_solana_safety(goplus, rug)
    assert not merged.ok


def test_settings_entry_chains_default_sol_only():
    s = Settings(entry_chains=("solana",), scan_chains=("solana",))
    assert s.entry_allowed("solana")
    assert not s.entry_allowed("arbitrum")
