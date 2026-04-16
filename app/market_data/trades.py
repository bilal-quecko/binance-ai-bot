"""Trade models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TradeTick:
    symbol: str
    price: float
    quantity: float
    timestamp: datetime
