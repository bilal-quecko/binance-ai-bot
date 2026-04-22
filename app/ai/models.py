"""Typed advisory AI signal models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


Bias = Literal["bullish", "bearish", "sideways"]
SuggestedAction = Literal["wait", "enter", "hold", "exit", "abstain"]
AIRegime = Literal[
    "trending",
    "ranging",
    "choppy",
    "breakout_building",
    "reversal_risk",
    "high_volatility_unstable",
    "insufficient_data",
]
NoiseLevel = Literal["low", "moderate", "high", "extreme", "unknown"]
HorizonName = Literal["5m", "15m", "1h"]


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
    return_5m: Decimal | None = None
    return_15m: Decimal | None = None
    return_1h: Decimal | None = None
    momentum_persistence: Decimal | None = None
    direction_flip_rate: Decimal | None = None
    structure_quality: Decimal | None = None
    technical_trend_direction: str | None = None
    technical_trend_strength: str | None = None
    technical_trend_strength_score: int | None = None
    volatility_regime: str | None = None
    breakout_readiness: str | None = None
    breakout_bias: str | None = None
    reversal_risk: str | None = None
    multi_timeframe_agreement: str | None = None
    market_state: str | None = None
    market_sentiment_score: int | None = None
    market_breadth_state: str | None = None
    selected_symbol_relative_strength: str | None = None
    recent_false_positive_rate_5m: Decimal | None = None
    recent_false_reversal_rate_5m: Decimal | None = None


@dataclass(slots=True)
class AIHorizonSignal:
    """Horizon-specific advisory view for short-term robustness."""

    horizon: HorizonName
    bias: Bias
    confidence: int
    suggested_action: SuggestedAction
    abstain: bool = False
    confirmation_needed: bool = False
    explanation: str = ""


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
    regime: AIRegime = "insufficient_data"
    noise_level: NoiseLevel = "unknown"
    abstain: bool = False
    low_confidence: bool = False
    confirmation_needed: bool = False
    preferred_horizon: HorizonName | None = None
    weakening_factors: tuple[str, ...] = field(default_factory=tuple)
    horizon_signals: tuple[AIHorizonSignal, ...] = field(default_factory=tuple)
