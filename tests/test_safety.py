from hibrit_trader.safety import _evm_decision, _solana_decision


def test_evm_temiz_token():
    r = _evm_decision({
        "is_honeypot": "0", "cannot_sell_all": "0",
        "buy_tax": "0.01", "sell_tax": "0.01",
        "is_open_source": "1", "hidden_owner": "0",
        "owner_change_balance": "0", "is_mintable": "0",
        "holders": [{"percent": "0.05"}] * 10,
    })
    assert r.ok and r.reasons == []


def test_evm_honeypot_red():
    r = _evm_decision({"is_honeypot": "1", "is_open_source": "1"})
    assert not r.ok
    assert "honeypot" in r.reasons


def test_evm_yuksek_vergi_red():
    r = _evm_decision({"is_open_source": "1", "sell_tax": "0.5"})
    assert not r.ok


def test_evm_holder_konsantrasyonu_red():
    r = _evm_decision({"is_open_source": "1", "holders": [{"percent": "0.09"}] * 10})
    assert not r.ok
    assert any("top10" in neden for neden in r.reasons)


def test_solana_mint_acik_red():
    r = _solana_decision({"mintable": {"status": "1"}})
    assert not r.ok


def test_solana_temiz():
    r = _solana_decision({
        "mintable": {"status": "0"}, "freezable": {"status": "0"},
        "holders": [{"percent": "3.0"}] * 10,
    })
    assert r.ok
