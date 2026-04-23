"""Typed models for symbol-scoped sentiment intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.market_data.candles import Candle


SentimentLabel = Literal["bullish", "bearish", "neutral", "mixed", "insufficient_data"]
MomentumState = Literal["rising", "fading", "stable", "unknown"]
RiskFlag = Literal["hype", "panic", "normal", "unknown"]
SentimentDataState = Literal["ready", "incomplete"]
SentimentSourceMode = Literal["proxy", "external", "mixed"]


@dataclass(slots=True)
class SentimentComponent:
    """One deterministic sentiment component used in the final score."""

    name: str
    score: Decimal
    weight: Decimal
    explanation: str


@dataclass(slots=True)
class SymbolSentimentContext:
    """Inputs available to symbol-scoped sentiment sources."""

    symbol: str
    generated_at: datetime
    candles: tuple[Candle, ...]
    benchmark_symbol: str | None = None
    benchmark_closes: tuple[Decimal, ...] = ()


@dataclass(slots=True)
class SymbolSentimentSnapshot:
    """Typed symbol-scoped sentiment output for workstation and fusion use."""

    symbol: str
    generated_at: datetime
    data_state: SentimentDataState
    status_message: str | None
    score: int | None
    label: SentimentLabel
    confidence: int | None
    momentum_state: MomentumState
    risk_flag: RiskFlag
    explanation: str
    source_mode: SentimentSourceMode
    components: tuple[SentimentComponent, ...]
