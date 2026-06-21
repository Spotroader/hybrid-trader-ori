"""Broker fabrikası — paper veya live."""

from __future__ import annotations

from hibrit_trader.config import Settings
from hibrit_trader.paper import PaperBroker


def make_broker(settings: Settings):
    if settings.mode == "live":
        if settings.sol_server_signing_enabled() or (
            settings.evm_private_key and settings.zero_x_api_key
        ):
            from hibrit_trader.live import LiveBroker
            return LiveBroker(settings)
        from hibrit_trader.phantom_broker import PhantomLiveBroker
        return PhantomLiveBroker(settings)
    return PaperBroker(start_balance_usd=settings.paper_start_balance_usd)
