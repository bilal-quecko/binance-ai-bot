"""Typed advisory AI signal models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


Bias = Literal["bullish", "bearish", "sideways"]
SuggestedAction = Literal["wait", "enter", "hold", "exit"]


@dataclass(slots=True)
class AIFeatureVector:
    """Deterministic feature vector used by the advisory scorer."""

    symbol: str
    timestamp: datetime
    candle_count: int
    close_price: Decimal
    ema_fast: Decimal | None
    ema_slow: Decimal | None
    rsi: Decimal | None
    atr: Decimal | None
    volatility_pct: Decimal | None
    momentum: Decimal | None
    recent_returns: tuple[Decimal, ...] = field(default_factory=tuple)
    wick_body_ratio: Decimal | None = None
    upper_wick_ratio: Decimal | None = None
    lower_wick_ratio: Decimal | None = None
    volume_change_pct: Decimal | None = None
    volume_spike_ratio: Decimal | None = None
    spread_ratio: Decimal | None = None
    order_book_imbalance: Decimal | None = None
    microstructure_healthy: bool = False


@dataclass(slots=True)
class AISignalSnapshot:
    """User-facing advisory AI signal output."""

    symbol: str
    bias: Bias
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: SuggestedAction
    explanation: str
    feature_vector: AIFeatureVector
