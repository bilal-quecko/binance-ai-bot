"""Trade parsing and normalized models."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping


def _from_millis(value: int) -> datetime:
    """Convert a millisecond Unix timestamp into a UTC datetime."""

    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(slots=True)
class TradeTick:
    """Normalized Binance Spot trade tick."""

    symbol: str
    trade_id: int
    price: Decimal
    quantity: Decimal
    event_time: datetime
    trade_time: datetime
    is_buyer_maker: bool


def parse_trade_payload(payload: Mapping[str, Any]) -> TradeTick:
    """Parse a Binance Spot trade or aggTrade payload into a normalized trade tick."""

    trade_id = payload.get("t", payload.get("a", 0))
    trade_time = payload.get("T", payload["E"])
    return TradeTick(
        symbol=str(payload["s"]),
        trade_id=int(trade_id),
        price=Decimal(str(payload["p"])),
        quantity=Decimal(str(payload["q"])),
        event_time=_from_millis(int(payload["E"])),
        trade_time=_from_millis(int(trade_time)),
        is_buyer_maker=bool(payload.get("m", False)),
    )
