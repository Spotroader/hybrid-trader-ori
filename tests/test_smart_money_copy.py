"""Alpha copy cluster — kısa pencere smart money."""

from hibrit_trader.scanner import Pair
from hibrit_trader.smart_money import copy_trade_min_wallets, copy_trade_window_sec


def test_copy_trade_defaults():
    assert copy_trade_window_sec() == 300
    assert copy_trade_min_wallets() == 2


def test_wallet_source_includes_copy_literal():
    from hibrit_trader import smart_money

    assert "copy" in smart_money.WalletSource.__args__
