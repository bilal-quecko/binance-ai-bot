"""Typed pattern-analysis models and summary helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal


PatternDataState = Literal["ready", "waiting_for_runtime", "waiting_for_history", "degraded_storage"]
PatternDirection = Literal["bullish", "bearish", "sideways"]
TrendCharacter = Literal["persistent", "balanced", "choppy"]
BreakoutTendency = Literal["breakout_prone", "range_bound", "mixed"]
ReversalTendency = Literal["elevated", "normal", "low", "unknown"]


@dataclass(slots=True)
class PatternPricePoint:
    """One timestamped close-price point used for horizon analysis."""

    symbol: str
    timestamp: datetime
    close_price: Decimal


@dataclass(slots=True)
class PatternAnalysisSnapshot:
    """Typed pattern-analysis output for one symbol and one horizon."""

    symbol: str
    horizon: str
    generated_at: datetime
    data_state: PatternDataState
    status_message: str | None
    coverage_start: datetime | None
    coverage_end: datetime | None
    coverage_ratio_pct: Decimal
    partial_coverage: bool
    overall_direction: PatternDirection | None
    net_return_pct: Decimal | None
    up_moves: int
    down_moves: int
    flat_moves: int
    up_move_ratio_pct: Decimal | None
    down_move_ratio_pct: Decimal | None
    realized_volatility_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    trend_character: TrendCharacter | None
    breakout_tendency: BreakoutTendency | None
    reversal_tendency: ReversalTendency | None
    explanation: str | None


def empty_pattern_snapshot(
    *,
    symbol: str,
    horizon: str,
    data_state: PatternDataState,
    status_message: str,
) -> PatternAnalysisSnapshot:
    """Return a typed empty pattern-analysis response."""

    return PatternAnalysisSnapshot(
        symbol=symbol,
        horizon=horizon,
        generated_at=datetime.now(tz=UTC),
        data_state=data_state,
        status_message=status_message,
        coverage_start=None,
        coverage_end=None,
        coverage_ratio_pct=Decimal("0"),
        partial_coverage=False,
        overall_direction=None,
        net_return_pct=None,
        up_moves=0,
        down_moves=0,
        flat_moves=0,
        up_move_ratio_pct=None,
        down_move_ratio_pct=None,
        realized_volatility_pct=None,
        max_drawdown_pct=None,
        trend_character=None,
        breakout_tendency=None,
        reversal_tendency=None,
        explanation=None,
    )
