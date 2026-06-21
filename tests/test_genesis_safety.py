"""Genesis paper güvenlik gevşetmesi."""

from hibrit_trader.safety import SafetyReport, entry_safety_ok


def test_genesis_allows_goplus_no_data(monkeypatch):
    monkeypatch.setenv("BOT_MODE", "paper")
    monkeypatch.setenv("GENESIS_SAFETY_LAX", "1")
    report = SafetyReport(ok=False, reasons=["GoPlus verisi yok"])
    ok, note = entry_safety_ok(report, genesis_ok=True)
    assert ok
    assert "genesis" in note


def test_genesis_blocks_honeypot(monkeypatch):
    monkeypatch.setenv("BOT_MODE", "paper")
    report = SafetyReport(ok=False, reasons=["honeypot"])
    ok, _ = entry_safety_ok(report, genesis_ok=True)
    assert not ok


def test_non_genesis_fail_closed():
    report = SafetyReport(ok=False, reasons=["GoPlus verisi yok"])
    ok, _ = entry_safety_ok(report, genesis_ok=False)
    assert not ok
