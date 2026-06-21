"""Holder concentration — RugCheck top holder filtre."""

from hibrit_trader.holder_risk import holder_report_from_payload


def test_holder_blocks_concentrated():
    data = {
        "topHolders": [
            {"pct": 50.0, "insider": False},
            {"pct": 20.0, "insider": False},
        ]
    }
    rep = holder_report_from_payload(data, genesis_ok=False)
    assert not rep.ok
    assert any("top1" in r for r in rep.reasons)


def test_genesis_relaxes_top1():
    data = {"topHolders": [{"pct": 50.0, "insider": False}]}
    rep = holder_report_from_payload(data, genesis_ok=True)
    assert rep.ok


def test_insider_cluster_blocks_standard():
    data = {
        "topHolders": [
            {"pct": 10, "insider": True},
            {"pct": 9, "insider": True},
            {"pct": 8, "insider": True},
        ]
    }
    rep = holder_report_from_payload(data, genesis_ok=False)
    assert not rep.ok
