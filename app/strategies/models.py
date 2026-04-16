"""Strategy models."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass(slots=True)
class StrategySignal:
    """Deterministic strategy decision output."""

    symbol: str
    side: Literal["BUY", "SELL", "HOLD"]
    confidence: Decimal
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class TrendFollowingConfig:
    """Configuration for the deterministic trend-following strategy."""

    min_atr_ratio: Decimal = Decimal("0.001")
    max_atr_ratio: Decimal = Decimal("0.05")
    max_spread_ratio: Decimal = Decimal("0.002")
    min_order_book_imbalance: Decimal = Decimal("-0.25")
    buy_confidence: Decimal = Decimal("0.60")
    hold_confidence: Decimal = Decimal("1.00")
