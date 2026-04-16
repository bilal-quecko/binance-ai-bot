"""Order book parsing and normalized models."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping


def _from_millis(value: int) -> datetime:
    """Convert a millisecond Unix timestamp into a UTC datetime."""

    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(slots=True)
class TopOfBook:
    """Normalized best bid/ask state."""

    symbol: str
    bid_price: Decimal
    bid_quantity: Decimal
    ask_price: Decimal
    ask_quantity: Decimal
    event_time: datetime


def parse_book_ticker_payload(payload: Mapping[str, Any]) -> TopOfBook:
    """Parse a Binance Spot book ticker payload into a normalized top-of-book."""

    raw_event_time = payload.get("E", payload.get("u", 0))
    return TopOfBook(
        symbol=str(payload["s"]),
        bid_price=Decimal(str(payload["b"])),
        bid_quantity=Decimal(str(payload["B"])),
        ask_price=Decimal(str(payload["a"])),
        ask_quantity=Decimal(str(payload["A"])),
        event_time=_from_millis(int(raw_event_time)),
    )
