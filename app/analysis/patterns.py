"""Breakout and reversal readiness heuristics."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


ReadinessLevel = Literal["low", "medium", "high", "unknown"]
BreakoutBias = Literal["upside", "downside", "none"]
TrendDirection = Literal["bullish", "bearish", "sideways"]
MomentumState = Literal["bullish", "bearish", "neutral", "overbought", "oversold", "unknown"]
VolatilityRegime = Literal["low", "normal", "high", "unknown"]


def assess_breakout_readiness(
    *,
    current_price: Decimal,
    trend_direction: TrendDirection,
    momentum_state: MomentumState,
    volatility_regime: VolatilityRegime,
    support_levels: list[Decimal],
    resistance_levels: list[Decimal],
) -> tuple[ReadinessLevel, BreakoutBias]:
    """Estimate breakout readiness from trend, momentum, and nearby structure."""

    if current_price <= Decimal("0"):
        return ("unknown", "none")

    nearest_resistance = next((level for level in resistance_levels if level > current_price), None)
    nearest_support = next((level for level in reversed(support_levels) if level < current_price), None)

    upside_distance = (
        (nearest_resistance - current_price) / current_price
        if nearest_resistance is not None
        else None
    )
    downside_distance = (
        (current_price - nearest_support) / current_price
        if nearest_support is not None
        else None
    )

    if trend_direction == "bullish" and momentum_state in {"bullish", "overbought"}:
        if upside_distance is not None and upside_distance <= Decimal("0.003"):
            return ("high", "upside")
        if upside_distance is not None and upside_distance <= Decimal("0.01"):
            return ("medium", "upside")
    if trend_direction == "bearish" and momentum_state in {"bearish", "oversold"}:
        if downside_distance is not None and downside_distance <= Decimal("0.003"):
            return ("high", "downside")
        if downside_distance is not None and downside_distance <= Decimal("0.01"):
            return ("medium", "downside")
    if volatility_regime == "high" and trend_direction in {"bullish", "bearish"}:
        return ("medium", "upside" if trend_direction == "bullish" else "downside")
    return ("low", "none")


def assess_reversal_risk(
    *,
    current_price: Decimal,
    trend_direction: TrendDirection,
    momentum_state: MomentumState,
    support_levels: list[Decimal],
    resistance_levels: list[Decimal],
) -> ReadinessLevel:
    """Estimate reversal risk from exhausted momentum near structure."""

    if current_price <= Decimal("0"):
        return "unknown"

    nearest_resistance = next((level for level in resistance_levels if level > current_price), None)
    nearest_support = next((level for level in reversed(support_levels) if level < current_price), None)

    if (
        trend_direction == "bullish"
        and momentum_state == "overbought"
        and nearest_resistance is not None
        and (nearest_resistance - current_price) / current_price <= Decimal("0.006")
    ):
        return "high"
    if (
        trend_direction == "bearish"
        and momentum_state == "oversold"
        and nearest_support is not None
        and (current_price - nearest_support) / current_price <= Decimal("0.006")
    ):
        return "high"
    if momentum_state in {"overbought", "oversold"}:
        return "medium"
    return "low"
