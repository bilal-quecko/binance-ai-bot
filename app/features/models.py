"""Feature models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(slots=True)
class FeatureConfig:
    """Configuration for deterministic feature generation."""

    ema_fast_period: int = 12
    ema_slow_period: int = 26
    rsi_period: int = 14
    atr_period: int = 14


@dataclass(slots=True)
class FeatureSnapshot:
    """Typed feature state derived from normalized market data."""

    symbol: str
    timestamp: datetime
    ema_fast: Decimal | None = None
    ema_slow: Decimal | None = None
    rsi: Decimal | None = None
    atr: Decimal | None = None
    mid_price: Decimal | None = None
    bid_ask_spread: Decimal | None = None
    order_book_imbalance: Decimal | None = None
    regime: Literal["bullish", "bearish", "neutral"] | None = None
