"""Interpret Binance force-liquidation events into advisory intelligence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.data.binance_liquidation_feed import BinanceLiquidationEvent
from app.market_data.candles import Candle
from app.monitoring.crowd_positioning import CrowdPositioningSnapshot
from app.monitoring.liquidity_zones import LiquidityZoneSnapshot

LiquidationSignal = Literal[
    "none",
    "cascade_down",
    "cascade_up",
    "exhaustion",
    "sweep_confirmation",
    "noise",
]
LiquidationIntensity = Literal["low", "medium", "high"]
DominantLiquidationSide = Literal["longs_liquidated", "shorts_liquidated", "balanced"]
InterpretationConfidence = Literal["low", "medium", "high"]


@dataclass(slots=True, frozen=True)
class LiquidationEventAggregation:
    """Rolling liquidation-event aggregate for one symbol."""

    liquidation_volume_long: Decimal
    liquidation_volume_short: Decimal
    imbalance_ratio: Decimal
    event_frequency: Decimal
    event_count: int
    intensity_score: LiquidationIntensity


@dataclass(slots=True, frozen=True)
class LiquidationIntelligenceSnapshot:
    """Advisory interpretation of event-based liquidation activity."""

    liquidation_signal: LiquidationSignal
    liquidation_intensity: LiquidationIntensity
    dominant_side: DominantLiquidationSide
    interpretation_confidence: InterpretationConfidence
    explanation: str
    liquidation_volume_long: Decimal = Decimal("0")
    liquidation_volume_short: Decimal = Decimal("0")
    imbalance_ratio: Decimal = Decimal("0")
    event_frequency: Decimal = Decimal("0")
    event_count: int = 0
    data_quality: str = "event_based"


NEUTRAL_LIQUIDATION_INTELLIGENCE = LiquidationIntelligenceSnapshot(
    liquidation_signal="none",
    liquidation_intensity="low",
    dominant_side="balanced",
    interpretation_confidence="low",
    explanation="No recent Binance force-liquidation events are available for this symbol.",
    data_quality="unavailable",
)


def interpret_liquidation_events(
    *,
    symbol: str,
    events: Sequence[BinanceLiquidationEvent],
    candles: Sequence[Candle] = (),
    liquidity_zones: LiquidityZoneSnapshot | None = None,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
    now: datetime | None = None,
) -> LiquidationIntelligenceSnapshot:
    """Convert recent force-order events into event-based advisory context."""

    del symbol
    resolved_now = now or _latest_event_time(events) or datetime.now(tz=UTC)
    medium_events = _window_events(events, now=resolved_now, seconds=300)
    if not medium_events:
        return NEUTRAL_LIQUIDATION_INTELLIGENCE

    medium = aggregate_liquidation_events(events=medium_events, window_seconds=300)
    short = aggregate_liquidation_events(
        events=_window_events(events, now=resolved_now, seconds=30),
        window_seconds=30,
    )
    dominant = _dominant_side(medium)
    price_move = _price_move_pct(candles)
    signal: LiquidationSignal = "noise"
    confidence: InterpretationConfidence = "low"

    if medium.intensity_score == "low" and medium.event_count <= 2:
        signal = "noise"
        explanation = "Recent force-order activity is too small or sparse to interpret."
    elif _sweep_confirmed(events=medium_events, zones=liquidity_zones, dominant=dominant):
        signal = "sweep_confirmation"
        confidence = "high" if medium.intensity_score == "high" else "medium"
        explanation = "Liquidation events occurred near a previously estimated liquidity sweep zone."
    elif _is_exhaustion(short=short, medium=medium, price_move=price_move):
        signal = "exhaustion"
        confidence = "medium" if medium.intensity_score == "high" else "low"
        explanation = "A liquidation spike occurred while price movement stalled, suggesting possible exhaustion."
    elif (
        medium.intensity_score == "high"
        and dominant == "longs_liquidated"
        and medium.imbalance_ratio <= Decimal("-60")
        and price_move <= Decimal("-0.15")
    ):
        signal = "cascade_down"
        confidence = _cascade_confidence(medium, crowd_positioning)
        explanation = "Long liquidations dominate while price is moving down; downside cascade risk is active."
    elif (
        medium.intensity_score == "high"
        and dominant == "shorts_liquidated"
        and medium.imbalance_ratio >= Decimal("60")
        and price_move >= Decimal("0.15")
    ):
        signal = "cascade_up"
        confidence = _cascade_confidence(medium, crowd_positioning)
        explanation = "Short liquidations dominate while price is moving up; short-squeeze cascade risk is active."
    else:
        signal = "noise" if medium.intensity_score == "low" else "none"
        confidence = "medium" if medium.intensity_score == "medium" else "low"
        explanation = "Liquidation activity is present but does not form a clear cascade, exhaustion, or sweep read."

    return LiquidationIntelligenceSnapshot(
        liquidation_signal=signal,
        liquidation_intensity=medium.intensity_score,
        dominant_side=dominant,
        interpretation_confidence=confidence,
        explanation=explanation,
        liquidation_volume_long=medium.liquidation_volume_long,
        liquidation_volume_short=medium.liquidation_volume_short,
        imbalance_ratio=medium.imbalance_ratio,
        event_frequency=medium.event_frequency,
        event_count=medium.event_count,
    )


def aggregate_liquidation_events(
    *,
    events: Sequence[BinanceLiquidationEvent],
    window_seconds: int,
) -> LiquidationEventAggregation:
    """Aggregate liquidation volume, imbalance, and frequency."""

    long_volume = sum(
        (event.notional_value for event in events if _liquidated_position_side(event.side) == "long"),
        Decimal("0"),
    )
    short_volume = sum(
        (event.notional_value for event in events if _liquidated_position_side(event.side) == "short"),
        Decimal("0"),
    )
    total = long_volume + short_volume
    imbalance = Decimal("0") if total <= 0 else ((short_volume - long_volume) / total) * Decimal("100")
    frequency = Decimal(len(events)) / (Decimal(max(1, window_seconds)) / Decimal("60"))
    intensity = _intensity(total=total, event_count=len(events), frequency=frequency, imbalance=imbalance)
    return LiquidationEventAggregation(
        liquidation_volume_long=_quantize(long_volume),
        liquidation_volume_short=_quantize(short_volume),
        imbalance_ratio=imbalance.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        event_frequency=frequency.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        event_count=len(events),
        intensity_score=intensity,
    )


def liquidation_intelligence_line(snapshot: LiquidationIntelligenceSnapshot | None) -> str:
    """Return concise UI wording for liquidation intelligence."""

    signal = (snapshot or NEUTRAL_LIQUIDATION_INTELLIGENCE).liquidation_signal
    if signal == "cascade_down":
        return "Liquidation: Downside cascade in progress"
    if signal == "cascade_up":
        return "Liquidation: Short squeeze active"
    if signal == "exhaustion":
        return "Liquidation: Exhaustion detected"
    if signal == "sweep_confirmation":
        return "Liquidation: Sweep confirmation"
    return "Liquidation: No significant activity"


def _window_events(
    events: Sequence[BinanceLiquidationEvent],
    *,
    now: datetime,
    seconds: int,
) -> tuple[BinanceLiquidationEvent, ...]:
    cutoff = now - timedelta(seconds=seconds)
    return tuple(event for event in events if cutoff <= event.event_time <= now)


def _latest_event_time(events: Sequence[BinanceLiquidationEvent]) -> datetime | None:
    if not events:
        return None
    return max(event.event_time for event in events)


def _liquidated_position_side(order_side: str) -> Literal["long", "short", "unknown"]:
    if order_side.upper() == "SELL":
        return "long"
    if order_side.upper() == "BUY":
        return "short"
    return "unknown"


def _dominant_side(aggregation: LiquidationEventAggregation) -> DominantLiquidationSide:
    long_volume = aggregation.liquidation_volume_long
    short_volume = aggregation.liquidation_volume_short
    if long_volume > short_volume * Decimal("1.35"):
        return "longs_liquidated"
    if short_volume > long_volume * Decimal("1.35"):
        return "shorts_liquidated"
    return "balanced"


def _price_move_pct(candles: Sequence[Candle]) -> Decimal:
    recent = list(candles[-6:])
    if len(recent) < 2 or recent[0].close <= Decimal("0"):
        return Decimal("0")
    return (((recent[-1].close - recent[0].close) / recent[0].close) * Decimal("100")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _intensity(
    *,
    total: Decimal,
    event_count: int,
    frequency: Decimal,
    imbalance: Decimal,
) -> LiquidationIntensity:
    if total < Decimal("1000") and event_count <= 1:
        return "low"
    if (
        total >= Decimal("100000")
        or event_count >= 8
        or (frequency >= Decimal("2.0") and total >= Decimal("25000"))
        or (abs(imbalance) >= Decimal("75") and total >= Decimal("50000"))
    ):
        return "high"
    if (
        total >= Decimal("25000")
        or event_count >= 3
        or (frequency >= Decimal("0.8") and total >= Decimal("10000"))
        or (abs(imbalance) >= Decimal("45") and total >= Decimal("10000"))
    ):
        return "medium"
    return "low"


def _is_exhaustion(
    *,
    short: LiquidationEventAggregation,
    medium: LiquidationEventAggregation,
    price_move: Decimal,
) -> bool:
    spike = short.intensity_score == "high" or short.event_count >= 5
    large_medium = medium.intensity_score == "high"
    return (spike or large_medium) and abs(price_move) <= Decimal("0.12")


def _sweep_confirmed(
    *,
    events: Sequence[BinanceLiquidationEvent],
    zones: LiquidityZoneSnapshot | None,
    dominant: DominantLiquidationSide,
) -> bool:
    if zones is None or zones.sweep_risk == "none":
        return False
    if zones.sweep_risk == "downside_sweep" and dominant != "longs_liquidated":
        return False
    if zones.sweep_risk == "upside_sweep" and dominant != "shorts_liquidated":
        return False
    target = (
        zones.downside_liquidity_zone.level
        if zones.sweep_risk == "downside_sweep"
        else zones.upside_liquidity_zone.level
    )
    if target is None:
        return False
    return any(_within_pct(_event_price(event), target, Decimal("0.85")) for event in events)


def _event_price(event: BinanceLiquidationEvent) -> Decimal:
    return event.average_price if event.average_price > 0 else event.price


def _within_pct(left: Decimal, right: Decimal, pct: Decimal) -> bool:
    base = max(abs(left), abs(right), Decimal("0.00000001"))
    return (abs(left - right) / base) * Decimal("100") <= pct


def _cascade_confidence(
    aggregation: LiquidationEventAggregation,
    crowd: CrowdPositioningSnapshot | None,
) -> InterpretationConfidence:
    if aggregation.intensity_score != "high":
        return "medium"
    if crowd is not None and crowd.crowd_strength == "high":
        return "high"
    return "medium"


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
