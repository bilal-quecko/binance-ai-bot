"""Candle parsing and normalized models."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping


def _from_millis(value: int) -> datetime:
    """Convert a millisecond Unix timestamp into a UTC datetime."""

    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(slots=True)
class Candle:
    """Normalized kline/candle payload."""

    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    open_time: datetime
    close_time: datetime
    event_time: datetime
    trade_count: int
    is_closed: bool


def parse_kline_payload(payload: Mapping[str, Any]) -> Candle:
    """Parse a Binance Spot kline websocket payload into a normalized candle."""

    kline = payload["k"]
    return Candle(
        symbol=str(payload["s"]),
        timeframe=str(kline["i"]),
        open=Decimal(str(kline["o"])),
        high=Decimal(str(kline["h"])),
        low=Decimal(str(kline["l"])),
        close=Decimal(str(kline["c"])),
        volume=Decimal(str(kline["v"])),
        quote_volume=Decimal(str(kline["q"])),
        open_time=_from_millis(int(kline["t"])),
        close_time=_from_millis(int(kline["T"])),
        event_time=_from_millis(int(payload["E"])),
        trade_count=int(kline["n"]),
        is_closed=bool(kline["x"]),
    )
