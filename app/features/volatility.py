"""Volatility feature helpers."""

from collections.abc import Sequence
from decimal import Decimal

from app.features.indicators import atr
from app.market_data.candles import Candle


def build_atr(candles: Sequence[Candle], period: int) -> Decimal | None:
    """Return ATR for the provided candle history."""

    return atr(candles, period=period)
