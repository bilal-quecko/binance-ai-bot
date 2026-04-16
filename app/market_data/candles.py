"""Candle cache placeholder."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Candle:
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_time: datetime
