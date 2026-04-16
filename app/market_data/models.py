"""Market data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    timestamp: datetime
