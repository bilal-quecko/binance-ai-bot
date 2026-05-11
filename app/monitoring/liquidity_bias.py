"""Liquidity-positioning bias estimates for advisory decision layers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.market_data.candles import Candle
from app.monitoring.crowd_positioning import CrowdPositioningSnapshot


LiquidityBias = Literal["bullish", "bearish", "neutral"]
LiquidityPressure = Literal["low", "medium", "high"]
LiquidationDirection = Literal["up", "down", "none"]
TrapRisk = Literal["long_trap", "short_trap", "low"]


@dataclass(slots=True, frozen=True)
class LiquidityBiasSnapshot:
    """Estimated leverage-positioning context without exact liquidation data."""

    liquidity_bias: LiquidityBias
    liquidity_pressure: LiquidityPressure
    likely_liquidation_direction: LiquidationDirection
    trap_risk: TrapRisk
    explanation: str


@dataclass(slots=True, frozen=True)
class LiquidityBiasInput:
    """Inputs for estimated liquidity-positioning analysis."""

    symbol: str
    candles: Sequence[Candle]
    funding_rate: Decimal | None = None
    open_interest_change_pct: Decimal | None = None
    volatility_regime: str | None = None
    crowd_positioning: CrowdPositioningSnapshot | None = None


NEUTRAL_LIQUIDITY_BIAS = LiquidityBiasSnapshot(
    liquidity_bias="neutral",
    liquidity_pressure="low",
    likely_liquidation_direction="none",
    trap_risk="low",
    explanation="Liquidity positioning is neutral; funding and open-interest evidence is unavailable or balanced.",
)


def estimate_liquidity_bias(context: LiquidityBiasInput) -> LiquidityBiasSnapshot:
    """Estimate where leveraged positioning may be vulnerable.

    This intentionally uses coarse, explainable inputs. Exact liquidation maps are not required.
    """

    funding = context.funding_rate
    oi_change = context.open_interest_change_pct
    if context.crowd_positioning is not None:
        crowd = context.crowd_positioning
        if crowd.crowd_side == "long_crowded":
            return LiquidityBiasSnapshot(
                liquidity_bias="bearish",
                liquidity_pressure=_pressure_from_crowd(crowd.crowd_strength),
                likely_liquidation_direction="down",
                trap_risk="long_trap",
                explanation=f"Liquidity estimate uses Binance funding/OI crowd positioning: {crowd.explanation}",
            )
        if crowd.crowd_side == "short_crowded":
            return LiquidityBiasSnapshot(
                liquidity_bias="bullish",
                liquidity_pressure=_pressure_from_crowd(crowd.crowd_strength),
                likely_liquidation_direction="up",
                trap_risk="short_trap",
                explanation=f"Liquidity estimate uses Binance funding/OI crowd positioning: {crowd.explanation}",
            )
    oi_rising = oi_change is not None and oi_change > Decimal("0")
    range_compressed = _range_compressed(context.candles)
    price_change = _price_change_pct(context.candles)
    close_position = _close_position_in_recent_range(context.candles)

    if funding is not None and oi_rising:
        pressure = "high" if range_compressed or abs(oi_change or Decimal("0")) >= Decimal("5") else "medium"
        if funding > Decimal("0"):
            return LiquidityBiasSnapshot(
                liquidity_bias="bearish",
                liquidity_pressure=pressure,
                likely_liquidation_direction="down",
                trap_risk="long_trap",
                explanation=(
                    "Liquidity estimate: positive funding with rising open interest suggests crowded longs; "
                    "downside liquidation pressure is elevated."
                ),
            )
        if funding < Decimal("0"):
            return LiquidityBiasSnapshot(
                liquidity_bias="bullish",
                liquidity_pressure=pressure,
                likely_liquidation_direction="up",
                trap_risk="short_trap",
                explanation=(
                    "Liquidity estimate: negative funding with rising open interest suggests crowded shorts; "
                    "upside short-squeeze pressure is elevated."
                ),
            )

    if range_compressed and oi_rising:
        return LiquidityBiasSnapshot(
            liquidity_bias="neutral",
            liquidity_pressure="high",
            likely_liquidation_direction="none",
            trap_risk="low",
            explanation=(
                "Liquidity estimate: range compression with rising open interest suggests stored liquidation "
                "pressure, but direction is not confirmed."
            ),
        )

    if funding is None and oi_change is None:
        fallback = _structure_fallback(
            candles=context.candles,
            price_change=price_change,
            close_position=close_position,
            range_compressed=range_compressed,
            volatility_regime=context.volatility_regime,
        )
        if fallback is not None:
            return fallback

    if range_compressed:
        return LiquidityBiasSnapshot(
            liquidity_bias="neutral",
            liquidity_pressure="medium",
            likely_liquidation_direction="none",
            trap_risk="low",
            explanation=(
                "Liquidity estimate: recent range compression can create sweep risk, but funding and "
                "open-interest confirmation are unavailable."
            ),
        )

    return NEUTRAL_LIQUIDITY_BIAS


def _structure_fallback(
    *,
    candles: Sequence[Candle],
    price_change: Decimal,
    close_position: Decimal | None,
    range_compressed: bool,
    volatility_regime: str | None,
) -> LiquidityBiasSnapshot | None:
    if len(candles) < 12 or close_position is None:
        return None
    pressure: LiquidityPressure = "medium" if range_compressed else "low"
    if volatility_regime == "low" and range_compressed:
        pressure = "high"
    if price_change >= Decimal("2.0") and close_position >= Decimal("0.75") and range_compressed:
        return LiquidityBiasSnapshot(
            liquidity_bias="bearish",
            liquidity_pressure=pressure,
            likely_liquidation_direction="down",
            trap_risk="long_trap",
            explanation=(
                "Liquidity estimate: price is extended near recent range highs during compression; "
                "a downside long-trap sweep is possible."
            ),
        )
    if price_change <= Decimal("-2.0") and close_position <= Decimal("0.25") and range_compressed:
        return LiquidityBiasSnapshot(
            liquidity_bias="bullish",
            liquidity_pressure=pressure,
            likely_liquidation_direction="up",
            trap_risk="short_trap",
            explanation=(
                "Liquidity estimate: price is extended near recent range lows during compression; "
                "an upside short-squeeze sweep is possible."
            ),
        )
    return None


def _pressure_from_crowd(strength: str) -> LiquidityPressure:
    if strength == "high":
        return "high"
    if strength == "medium":
        return "medium"
    return "low"


def _price_change_pct(candles: Sequence[Candle]) -> Decimal:
    if len(candles) < 2 or candles[0].close <= Decimal("0"):
        return Decimal("0")
    return ((candles[-1].close - candles[0].close) / candles[0].close) * Decimal("100")


def _close_position_in_recent_range(candles: Sequence[Candle]) -> Decimal | None:
    recent = list(candles[-24:])
    if not recent:
        return None
    high = max(candle.high for candle in recent)
    low = min(candle.low for candle in recent)
    if high <= low:
        return None
    return (recent[-1].close - low) / (high - low)


def _range_compressed(candles: Sequence[Candle]) -> bool:
    if len(candles) < 24:
        return False
    recent = list(candles[-12:])
    prior = list(candles[-24:-12])
    recent_avg = _average_range(recent)
    prior_avg = _average_range(prior)
    latest_close = candles[-1].close
    if latest_close <= Decimal("0"):
        return False
    recent_range_pct = (recent_avg / latest_close) * Decimal("100")
    if prior_avg > Decimal("0") and recent_avg <= prior_avg * Decimal("0.65"):
        return True
    return recent_range_pct <= Decimal("0.75")


def _average_range(candles: Sequence[Candle]) -> Decimal:
    if not candles:
        return Decimal("0")
    return sum((candle.high - candle.low for candle in candles), Decimal("0")) / Decimal(len(candles))
