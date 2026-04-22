"""Technical analysis service for the selected symbol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.analysis.multi_timeframe import (
    AggregatedTimeframeSummary,
    build_multi_timeframe_summaries,
    summarize_multi_timeframe_agreement,
)
from app.analysis.patterns import (
    assess_breakout_readiness,
    assess_reversal_risk,
)
from app.analysis.support_resistance import (
    extract_resistance_levels,
    extract_support_levels,
)
from app.analysis.volatility import classify_volatility_regime
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle


AnalysisState = Literal["ready", "incomplete"]
TrendDirection = Literal["bullish", "bearish", "sideways"]
TrendStrength = Literal["weak", "moderate", "strong"]
MomentumState = Literal["bullish", "bearish", "neutral", "overbought", "oversold", "unknown"]
VolatilityRegime = Literal["low", "normal", "high", "unknown"]
ReadinessLevel = Literal["low", "medium", "high", "unknown"]
BreakoutBias = Literal["upside", "downside", "none"]
TimeframeAgreement = Literal[
    "bullish_alignment",
    "bearish_alignment",
    "mixed",
    "insufficient_data",
]


@dataclass(slots=True)
class TimeframeTechnicalSummary:
    """Trend summary for one derived timeframe."""

    timeframe: str
    trend_direction: TrendDirection
    trend_strength: TrendStrength


@dataclass(slots=True)
class TechnicalAnalysisSnapshot:
    """Typed technical analysis payload for the selected symbol."""

    symbol: str
    timestamp: datetime
    data_state: AnalysisState
    status_message: str | None
    trend_direction: TrendDirection | None
    trend_strength: TrendStrength | None
    trend_strength_score: int | None
    support_levels: list[Decimal]
    resistance_levels: list[Decimal]
    momentum_state: MomentumState | None
    volatility_regime: VolatilityRegime | None
    breakout_readiness: ReadinessLevel | None
    breakout_bias: BreakoutBias | None
    reversal_risk: ReadinessLevel | None
    multi_timeframe_agreement: TimeframeAgreement | None
    timeframe_summaries: list[TimeframeTechnicalSummary]
    explanation: str | None


class TechnicalAnalysisService:
    """Build symbol-scoped technical analysis from recent candles and features."""

    def analyze(
        self,
        *,
        symbol: str,
        candles: Sequence[Candle],
        feature_snapshot: FeatureSnapshot | None,
    ) -> TechnicalAnalysisSnapshot:
        """Return a technical view for one symbol."""

        if len(candles) < 6 or feature_snapshot is None:
            return TechnicalAnalysisSnapshot(
                symbol=symbol,
                timestamp=datetime.now(tz=UTC),
                data_state="incomplete",
                status_message=(
                    f"Technical analysis for {symbol} needs more closed candles before trend and structure can be assessed."
                ),
                trend_direction=None,
                trend_strength=None,
                trend_strength_score=None,
                support_levels=[],
                resistance_levels=[],
                momentum_state=None,
                volatility_regime=None,
                breakout_readiness=None,
                breakout_bias=None,
                reversal_risk=None,
                multi_timeframe_agreement=None,
                timeframe_summaries=[],
                explanation=None,
            )

        latest_candle = candles[-1]
        current_price = latest_candle.close
        trend_direction = _classify_trend_direction(feature_snapshot, candles)
        trend_strength_score = _trend_strength_score(feature_snapshot, candles)
        trend_strength = _classify_strength_from_score(trend_strength_score)
        momentum_state = _classify_momentum(feature_snapshot, candles)
        volatility_regime = classify_volatility_regime(
            atr=feature_snapshot.atr,
            price=current_price,
        )
        support_levels = extract_support_levels(candles, current_price=current_price)
        resistance_levels = extract_resistance_levels(candles, current_price=current_price)
        breakout_readiness, breakout_bias = assess_breakout_readiness(
            current_price=current_price,
            trend_direction=trend_direction,
            momentum_state=momentum_state,
            volatility_regime=volatility_regime,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )
        reversal_risk = assess_reversal_risk(
            current_price=current_price,
            trend_direction=trend_direction,
            momentum_state=momentum_state,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )
        timeframe_summaries = [
            TimeframeTechnicalSummary(
                timeframe=summary.timeframe,
                trend_direction=summary.trend_direction,
                trend_strength=summary.trend_strength,
            )
            for summary in build_multi_timeframe_summaries(candles)
        ]
        multi_timeframe_agreement = summarize_multi_timeframe_agreement(
            [
                AggregatedTimeframeSummary(
                    timeframe=summary.timeframe,
                    trend_direction=summary.trend_direction,
                    trend_strength=summary.trend_strength,
                )
                for summary in timeframe_summaries
            ]
        )

        explanation = _build_explanation(
            symbol=symbol,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            momentum_state=momentum_state,
            volatility_regime=volatility_regime,
            breakout_readiness=breakout_readiness,
            breakout_bias=breakout_bias,
            reversal_risk=reversal_risk,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            multi_timeframe_agreement=multi_timeframe_agreement,
        )

        return TechnicalAnalysisSnapshot(
            symbol=symbol,
            timestamp=feature_snapshot.timestamp,
            data_state="ready",
            status_message=f"Technical analysis is ready for {symbol}.",
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_strength_score=trend_strength_score,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            momentum_state=momentum_state,
            volatility_regime=volatility_regime,
            breakout_readiness=breakout_readiness,
            breakout_bias=breakout_bias,
            reversal_risk=reversal_risk,
            multi_timeframe_agreement=multi_timeframe_agreement,
            timeframe_summaries=timeframe_summaries,
            explanation=explanation,
        )


def _classify_trend_direction(
    feature_snapshot: FeatureSnapshot,
    candles: Sequence[Candle],
) -> TrendDirection:
    """Classify trend direction from the current feature snapshot."""

    latest_close = candles[-1].close
    if (
        feature_snapshot.ema_fast is not None
        and feature_snapshot.ema_slow is not None
        and latest_close > Decimal("0")
    ):
        ema_gap_ratio = abs(feature_snapshot.ema_fast - feature_snapshot.ema_slow) / latest_close
        if ema_gap_ratio < Decimal("0.003"):
            return "sideways"

    if abs(_momentum_pct(candles, lookback=5)) < Decimal("0.004"):
        return "sideways"
    if feature_snapshot.regime == "bullish":
        return "bullish"
    if feature_snapshot.regime == "bearish":
        return "bearish"
    return "sideways"


def _trend_strength_score(
    feature_snapshot: FeatureSnapshot,
    candles: Sequence[Candle],
) -> int:
    """Return an integer trend-strength score from 0 to 100."""

    latest_close = candles[-1].close
    ema_gap_ratio = Decimal("0")
    if (
        feature_snapshot.ema_fast is not None
        and feature_snapshot.ema_slow is not None
        and latest_close > Decimal("0")
    ):
        ema_gap_ratio = abs(feature_snapshot.ema_fast - feature_snapshot.ema_slow) / latest_close

    rsi_component = Decimal("0")
    if feature_snapshot.rsi is not None:
        rsi_component = abs(feature_snapshot.rsi - Decimal("50")) / Decimal("50")

    momentum_component = abs(_momentum_pct(candles, lookback=5))

    normalized = min(
        Decimal("1"),
        (ema_gap_ratio / Decimal("0.02")) * Decimal("0.45")
        + min(Decimal("1"), rsi_component) * Decimal("0.30")
        + min(Decimal("1"), momentum_component / Decimal("0.03")) * Decimal("0.25"),
    )
    return int((normalized * Decimal("100")).quantize(Decimal("1")))


def _classify_strength_from_score(score: int) -> TrendStrength:
    """Map a numeric trend score into a readable strength label."""

    if score >= 65:
        return "strong"
    if score >= 35:
        return "moderate"
    return "weak"


def _classify_momentum(
    feature_snapshot: FeatureSnapshot,
    candles: Sequence[Candle],
) -> MomentumState:
    """Classify momentum from RSI and recent return."""

    momentum_pct = _momentum_pct(candles, lookback=5)
    rsi = feature_snapshot.rsi
    if rsi is None:
        return "unknown"
    if rsi >= Decimal("70"):
        return "overbought"
    if rsi <= Decimal("30"):
        return "oversold"
    if rsi >= Decimal("55") and momentum_pct > Decimal("0"):
        return "bullish"
    if rsi <= Decimal("45") and momentum_pct < Decimal("0"):
        return "bearish"
    return "neutral"


def _momentum_pct(candles: Sequence[Candle], *, lookback: int) -> Decimal:
    """Return the recent close-to-close momentum percentage."""

    if len(candles) < lookback:
        return Decimal("0")
    base_close = candles[-lookback].close
    if base_close <= Decimal("0"):
        return Decimal("0")
    return (candles[-1].close - base_close) / base_close


def _build_explanation(
    *,
    symbol: str,
    trend_direction: TrendDirection,
    trend_strength: TrendStrength,
    momentum_state: MomentumState,
    volatility_regime: VolatilityRegime,
    breakout_readiness: ReadinessLevel,
    breakout_bias: BreakoutBias,
    reversal_risk: ReadinessLevel,
    support_levels: Sequence[Decimal],
    resistance_levels: Sequence[Decimal],
    multi_timeframe_agreement: TimeframeAgreement,
) -> str:
    """Build a human-readable technical explanation."""

    parts = [
        f"{symbol} is technically {trend_direction} with {trend_strength} trend strength.",
        f"Momentum is {momentum_state} and volatility is {volatility_regime}.",
    ]
    if support_levels:
        parts.append(f"Nearest support is around {support_levels[-1]}.")
    if resistance_levels:
        parts.append(f"Nearest resistance is around {resistance_levels[0]}.")
    if breakout_bias != "none":
        parts.append(
            f"Breakout readiness is {breakout_readiness} toward a {breakout_bias} move."
        )
    else:
        parts.append(f"Breakout readiness is {breakout_readiness}.")
    parts.append(f"Reversal risk is {reversal_risk}.")
    if multi_timeframe_agreement != "insufficient_data":
        parts.append(
            f"Multi-timeframe confirmation is {multi_timeframe_agreement.replace('_', ' ')}."
        )
    else:
        parts.append("Multi-timeframe confirmation still needs more history.")
    return " ".join(parts)
