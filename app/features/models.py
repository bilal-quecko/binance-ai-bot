"""Feature models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class FeatureSnapshot:
    symbol: str
    timestamp: datetime
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    atr: float | None = None
    regime: str | None = None
