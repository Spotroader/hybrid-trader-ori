from pathlib import Path

from hibrit_trader.killswitch import KILL_FILE, activate, deactivate, is_active


def test_kill_switch_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("hibrit_trader.killswitch.KILL_FILE", tmp_path / "KILL")
    assert not is_active()
    activate("test")
    assert is_active()
    deactivate()
    assert not is_active()
