"""Typed models for the unified advisory fusion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.ai.models import AISignalSnapshot
from app.analysis.pattern_summary import PatternAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.runner.models import TradeReadiness
from app.sentiment.models import SymbolSentimentSnapshot


FusionDataState = Literal["ready", "incomplete"]
FinalSignal = Literal["long", "short", "wait", "reduce_risk", "exit_long", "exit_short"]
RiskGrade = Literal["low", "medium", "high"]
PreferredHorizon = Literal["5m", "15m", "1h"]


@dataclass(slots=True)
class FusionInputs:
    """Inputs available to the unified signal fusion engine."""

    symbol: str
    technical_analysis: TechnicalAnalysisSnapshot | None
    pattern_analysis: PatternAnalysisSnapshot | None
    ai_signal: AISignalSnapshot | None
    symbol_sentiment: SymbolSentimentSnapshot | None
    trade_readiness: TradeReadiness | None
    current_position_quantity: Decimal = Decimal("0")


@dataclass(slots=True)
class FusionSignalSnapshot:
    """Unified advisory output for one selected symbol."""

    symbol: str
    generated_at: datetime
    data_state: FusionDataState
    status_message: str | None
    final_signal: FinalSignal
    confidence: int
    expected_edge_pct: Decimal | None
    preferred_horizon: PreferredHorizon
    risk_grade: RiskGrade
    alignment_score: int
    top_reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    invalidation_hint: str | None = None


def empty_fusion_snapshot(
    *,
    symbol: str,
    status_message: str,
    final_signal: FinalSignal = "wait",
    preferred_horizon: PreferredHorizon = "15m",
    risk_grade: RiskGrade = "high",
) -> FusionSignalSnapshot:
    """Return a typed empty fusion snapshot."""

    return FusionSignalSnapshot(
        symbol=symbol,
        generated_at=datetime.now(tz=UTC),
        data_state="incomplete",
        status_message=status_message,
        final_signal=final_signal,
        confidence=0,
        expected_edge_pct=None,
        preferred_horizon=preferred_horizon,
        risk_grade=risk_grade,
        alignment_score=0,
        top_reasons=(),
        warnings=(),
        invalidation_hint=None,
    )
