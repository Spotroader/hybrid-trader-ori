from hibrit_trader.scanner import parse_pool

ORNEK_HAVUZ = {
    "id": "solana_PoolAdres123",
    "attributes": {
        "name": "WIF / SOL",
        "base_token_price_usd": "1.25",
        "reserve_in_usd": "500000",
        "volume_usd": {"m5": "10000", "h1": "90000", "h24": "1200000"},
        "price_change_percentage": {"m5": "1.2", "h1": "5.5", "h24": "12.0"},
        "transactions": {"h1": {"buys": 120, "sells": 80}},
    },
    "relationships": {
        "base_token": {"data": {"id": "solana_TokenAdres456"}},
        "dex": {"data": {"id": "raydium"}},
    },
}


def test_parse_pool_normalize():
    p = parse_pool("solana", ORNEK_HAVUZ)
    assert p is not None
    assert p.pool_address == "PoolAdres123"
    assert p.token_address == "TokenAdres456"
    assert p.dex == "raydium"
    assert p.price_usd == 1.25
    assert p.liquidity_usd == 500000
    assert p.vol_h1 == 90000
    assert p.txns_h1 == 200


def test_parse_pool_bozuk_kayit_none():
    assert parse_pool("solana", {"id": "x"}) is None


def test_parse_pool_eksik_alanlar_sifir():
    havuz = {
        "id": "base_P",
        "attributes": {"name": "A / B"},
        "relationships": {
            "base_token": {"data": {"id": "base_T"}},
            "dex": {"data": {"id": "uniswap"}},
        },
    }
    p = parse_pool("base", havuz)
    assert p is not None
    assert p.vol_h1 == 0.0 and p.liquidity_usd == 0.0
