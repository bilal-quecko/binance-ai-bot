"""Normalized market data models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook
from app.market_data.trades import TradeTick


@dataclass(slots=True)
class MarketSnapshot:
    """Latest normalized market state for a symbol."""

    symbol: str
    trade: TradeTick | None = None
    top_of_book: TopOfBook | None = None
    candle: Candle | None = None
    last_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    event_time: datetime | None = None
    received_at: datetime | None = None
    is_stale: bool = False
