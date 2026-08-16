"""Paper-only Futures models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

FuturesSide = Literal["LONG", "SHORT"]
FuturesOrderSide = Literal["LONG", "SHORT", "CLOSE"]
FuturesSignalSide = Literal["LONG", "SHORT", "WAIT", "AVOID", "CLOSE_LONG", "CLOSE_SHORT"]


@dataclass(slots=True)
class FuturesPosition:
    """Current paper Futures position."""

    symbol: str
    side: FuturesSide
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    leverage: int
    margin_mode: Literal["isolated"]
    margin_used: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price_estimate: Decimal
    opened_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class FuturesOrderRequest:
    """Paper-only Futures order request."""

    symbol: str
    side: FuturesOrderSide
    quantity: Decimal
    market_price: Decimal
    leverage: int = 2
    mode: Literal["paper"] = "paper"


@dataclass(slots=True)
class FuturesFillResult:
    """Paper-only Futures fill result."""

    order_id: str
    status: Literal["executed", "rejected"]
    symbol: str
    side: FuturesOrderSide
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class FuturesSignalInput:
    """Inputs for deterministic Futures signal evaluation."""

    symbol: str
    technical_bias: Literal["bullish", "bearish", "mixed", "neutral", "insufficient"] = "neutral"
    regime: Literal["bullish", "bearish", "range", "volatile", "insufficient_data", "unknown"] = "unknown"
    market_sentiment: Literal["bullish", "bearish", "neutral", "unknown"] = "unknown"
    symbol_sentiment: Literal["bullish", "bearish", "neutral", "unknown"] = "unknown"
    pattern_bias: Literal["bullish", "bearish", "mixed", "neutral", "unknown"] = "unknown"
    volatility_safe: bool = True
    spread_safe: bool = True
    expected_edge_pct: Decimal | None = None
    estimated_cost_pct: Decimal = Decimal("0")
    validation_score: Decimal | None = None
    current_position_side: FuturesSide | None = None
    long_invalidation: bool = False
    short_invalidation: bool = False
    liquidation_distance_pct: Decimal | None = None


@dataclass(slots=True)
class FuturesSignal:
    """Deterministic Futures signal."""

    symbol: str
    side: FuturesSignalSide
    confidence: int
    risk_grade: Literal["low", "medium", "high"]
    reason_codes: tuple[str, ...]
    blocker_reason: str | None = None
