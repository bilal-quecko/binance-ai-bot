"""Estimated liquidity-zone detection and TP/SL alignment helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.market_data.candles import Candle
from app.monitoring.crowd_positioning import CrowdPositioningSnapshot
from app.monitoring.liquidity_bias import LiquidityBiasSnapshot, NEUTRAL_LIQUIDITY_BIAS


ZoneStrength = Literal["low", "medium", "high"]
TargetDirection = Literal["up", "down", "none"]
SweepRisk = Literal["none", "upside_sweep", "downside_sweep", "both_sides"]
TradeTimingAdjustment = Literal["enter_now", "wait_for_sweep", "wait_for_confirmation", "avoid_chop"]
TpSlAlignment = Literal[
    "aligned",
    "stop_too_close_to_liquidity",
    "target_before_liquidity",
    "target_after_liquidity",
    "needs_review",
]
TradeDirection = Literal["long", "short", "wait", "avoid", "buy", "sell_exit", "none"]


@dataclass(slots=True, frozen=True)
class LiquidityZone:
    """Estimated area where stops or breakout liquidity may sit."""

    level: Decimal | None
    strength: ZoneStrength
    reason: str


@dataclass(slots=True, frozen=True)
class NearestLiquidityTarget:
    """Nearest estimated liquidity target relative to current price."""

    direction: TargetDirection
    level: Decimal | None
    distance_pct: Decimal | None
    strength: ZoneStrength


@dataclass(slots=True, frozen=True)
class LiquidityZoneSnapshot:
    """Estimated liquidity zones and execution-context interpretation."""

    upside_liquidity_zone: LiquidityZone
    downside_liquidity_zone: LiquidityZone
    nearest_liquidity_target: NearestLiquidityTarget
    sweep_risk: SweepRisk
    trade_timing_adjustment: TradeTimingAdjustment
    tp_sl_alignment: TpSlAlignment
    explanation: str


NEUTRAL_LIQUIDITY_ZONE = LiquidityZone(level=None, strength="low", reason="No clear estimated liquidity zone.")
NEUTRAL_LIQUIDITY_TARGET = NearestLiquidityTarget(
    direction="none",
    level=None,
    distance_pct=None,
    strength="low",
)
NEUTRAL_LIQUIDITY_ZONES = LiquidityZoneSnapshot(
    upside_liquidity_zone=NEUTRAL_LIQUIDITY_ZONE,
    downside_liquidity_zone=NEUTRAL_LIQUIDITY_ZONE,
    nearest_liquidity_target=NEUTRAL_LIQUIDITY_TARGET,
    sweep_risk="none",
    trade_timing_adjustment="wait_for_confirmation",
    tp_sl_alignment="needs_review",
    explanation="Liquidity zones are unavailable because recent candle structure is insufficient.",
)


def estimate_liquidity_zones(
    *,
    symbol: str,
    candles: Sequence[Candle],
    current_price: Decimal | None = None,
    trade_direction: TradeDirection = "none",
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    liquidity_bias: LiquidityBiasSnapshot | None = None,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
    regime_label: str | None = None,
    atr: Decimal | None = None,
) -> LiquidityZoneSnapshot:
    """Estimate liquidity zones and TP/SL alignment without exact liquidation maps."""

    del symbol
    if len(candles) < 8:
        return NEUTRAL_LIQUIDITY_ZONES
    price = current_price or candles[-1].close
    if price <= Decimal("0"):
        return NEUTRAL_LIQUIDITY_ZONES

    recent = list(candles[-48:])
    buffer_pct = _buffer_pct(price=price, candles=recent, atr=atr)
    upside = _upside_zone(recent=recent, current_price=price, buffer_pct=buffer_pct)
    downside = _downside_zone(recent=recent, current_price=price, buffer_pct=buffer_pct)
    nearest = _nearest_target(price=price, upside=upside, downside=downside, crowd_positioning=crowd_positioning)
    bias = liquidity_bias or NEUTRAL_LIQUIDITY_BIAS
    compressed = _range_compressed(recent)
    sweep_risk = _sweep_risk(
        price=price,
        upside=upside,
        downside=downside,
        bias=bias,
        buffer_pct=buffer_pct,
        compressed=compressed,
    )
    timing = _trade_timing(
        direction=trade_direction,
        sweep_risk=sweep_risk,
        nearest=nearest,
        regime_label=regime_label,
        compressed=compressed,
    )
    alignment = _tp_sl_alignment(
        direction=trade_direction,
        price=price,
        upside=upside,
        downside=downside,
        stop_loss=stop_loss,
        take_profit=take_profit,
        buffer_pct=buffer_pct,
    )

    return LiquidityZoneSnapshot(
        upside_liquidity_zone=upside,
        downside_liquidity_zone=downside,
        nearest_liquidity_target=nearest,
        sweep_risk=sweep_risk,
        trade_timing_adjustment=timing,
        tp_sl_alignment=alignment,
        explanation=_explanation(upside=upside, downside=downside, nearest=nearest, sweep_risk=sweep_risk, alignment=alignment),
    )


def validate_liquidity_zones_with_liquidations(
    *,
    zones: LiquidityZoneSnapshot,
    liquidation_signal: str,
    dominant_side: str,
) -> LiquidityZoneSnapshot:
    """Raise zone confidence when event-based liquidations confirm a sweep estimate."""

    if liquidation_signal != "sweep_confirmation":
        return zones
    if zones.sweep_risk == "downside_sweep" and dominant_side == "longs_liquidated":
        downside = _validated_zone(zones.downside_liquidity_zone)
        nearest = _validated_nearest_target(zones=zones, direction="down", zone=downside)
        return replace(
            zones,
            downside_liquidity_zone=downside,
            nearest_liquidity_target=nearest,
            trade_timing_adjustment="wait_for_confirmation",
            explanation=(
                f"{zones.explanation} Recent event-based liquidation events from long liquidations "
                "validate the downside sweep zone."
            ),
        )
    if zones.sweep_risk == "upside_sweep" and dominant_side == "shorts_liquidated":
        upside = _validated_zone(zones.upside_liquidity_zone)
        nearest = _validated_nearest_target(zones=zones, direction="up", zone=upside)
        return replace(
            zones,
            upside_liquidity_zone=upside,
            nearest_liquidity_target=nearest,
            trade_timing_adjustment="wait_for_confirmation",
            explanation=(
                f"{zones.explanation} Recent event-based liquidation events from short liquidations "
                "validate the upside sweep zone."
            ),
        )
    return zones


def _upside_zone(*, recent: Sequence[Candle], current_price: Decimal, buffer_pct: Decimal) -> LiquidityZone:
    highs = [candle.high for candle in recent]
    candidates = [high for high in highs if high >= current_price]
    if not candidates:
        candidates = highs
    range_high = max(candidates)
    equal_count = _cluster_count(highs, range_high, buffer_pct)
    swing_count = sum(1 for high in _swing_highs(recent) if _within_pct(high, range_high, buffer_pct))
    strength = _strength(equal_count=equal_count, swing_count=swing_count, is_range_extreme=True)
    reason = "Estimated upside liquidity near recent range highs"
    if equal_count >= 2:
        reason = "Estimated upside liquidity from equal highs and range-high stops"
    elif swing_count >= 2:
        reason = "Estimated upside liquidity from clustered swing highs"
    return LiquidityZone(level=_rounded_level(range_high), strength=strength, reason=reason)


def _downside_zone(*, recent: Sequence[Candle], current_price: Decimal, buffer_pct: Decimal) -> LiquidityZone:
    lows = [candle.low for candle in recent]
    candidates = [low for low in lows if low <= current_price]
    if not candidates:
        candidates = lows
    range_low = min(candidates)
    equal_count = _cluster_count(lows, range_low, buffer_pct)
    swing_count = sum(1 for low in _swing_lows(recent) if _within_pct(low, range_low, buffer_pct))
    strength = _strength(equal_count=equal_count, swing_count=swing_count, is_range_extreme=True)
    reason = "Estimated downside liquidity near recent range lows"
    if equal_count >= 2:
        reason = "Estimated downside liquidity from equal lows and range-low stops"
    elif swing_count >= 2:
        reason = "Estimated downside liquidity from clustered swing lows"
    return LiquidityZone(level=_rounded_level(range_low), strength=strength, reason=reason)


def _nearest_target(
    *,
    price: Decimal,
    upside: LiquidityZone,
    downside: LiquidityZone,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
) -> NearestLiquidityTarget:
    up_distance = _distance_pct(price=price, level=upside.level)
    down_distance = _distance_pct(price=price, level=downside.level)
    if up_distance is None and down_distance is None:
        return NEUTRAL_LIQUIDITY_TARGET
    if crowd_positioning is not None:
        if crowd_positioning.crowd_side == "long_crowded" and down_distance is not None:
            return NearestLiquidityTarget(direction="down", level=downside.level, distance_pct=down_distance, strength=downside.strength)
        if crowd_positioning.crowd_side == "short_crowded" and up_distance is not None:
            return NearestLiquidityTarget(direction="up", level=upside.level, distance_pct=up_distance, strength=upside.strength)
    if down_distance is None or (up_distance is not None and up_distance <= down_distance):
        return NearestLiquidityTarget(direction="up", level=upside.level, distance_pct=up_distance, strength=upside.strength)
    return NearestLiquidityTarget(direction="down", level=downside.level, distance_pct=down_distance, strength=downside.strength)


def _sweep_risk(
    *,
    price: Decimal,
    upside: LiquidityZone,
    downside: LiquidityZone,
    bias: LiquidityBiasSnapshot,
    buffer_pct: Decimal,
    compressed: bool,
) -> SweepRisk:
    near_up = _distance_pct(price=price, level=upside.level)
    near_down = _distance_pct(price=price, level=downside.level)
    up_near = near_up is not None and near_up <= max(Decimal("0.85"), buffer_pct * Decimal("2"))
    down_near = near_down is not None and near_down <= max(Decimal("0.85"), buffer_pct * Decimal("2"))
    strong_up = upside.strength == "high" or bias.likely_liquidation_direction == "up"
    strong_down = downside.strength == "high" or bias.likely_liquidation_direction == "down"
    if compressed and upside.strength in {"medium", "high"} and downside.strength in {"medium", "high"}:
        return "both_sides"
    if up_near and strong_up:
        return "upside_sweep"
    if down_near and strong_down:
        return "downside_sweep"
    return "none"


def _trade_timing(
    *,
    direction: TradeDirection,
    sweep_risk: SweepRisk,
    nearest: NearestLiquidityTarget,
    regime_label: str | None,
    compressed: bool,
) -> TradeTimingAdjustment:
    if sweep_risk == "both_sides" and (regime_label == "choppy" or compressed):
        return "avoid_chop"
    if direction in {"long", "buy"} and sweep_risk == "downside_sweep":
        return "wait_for_sweep"
    if direction == "short" and sweep_risk == "upside_sweep":
        return "wait_for_sweep"
    if direction in {"long", "buy"} and nearest.direction == "up":
        return "enter_now" if nearest.strength in {"medium", "high"} else "wait_for_confirmation"
    if direction == "short" and nearest.direction == "down":
        return "enter_now" if nearest.strength in {"medium", "high"} else "wait_for_confirmation"
    return "wait_for_confirmation"


def _tp_sl_alignment(
    *,
    direction: TradeDirection,
    price: Decimal,
    upside: LiquidityZone,
    downside: LiquidityZone,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    buffer_pct: Decimal,
) -> TpSlAlignment:
    if direction not in {"long", "buy", "short"} or stop_loss is None or take_profit is None:
        return "needs_review"
    danger_distance = max(Decimal("0.50"), buffer_pct)
    if direction in {"long", "buy"}:
        if downside.level is not None and _distance_between_pct(stop_loss, downside.level) <= danger_distance:
            return "stop_too_close_to_liquidity"
        if upside.level is None:
            return "needs_review"
        if take_profit < upside.level and _distance_between_pct(take_profit, upside.level) > danger_distance:
            return "target_before_liquidity"
        if take_profit >= upside.level:
            return "aligned" if take_profit <= upside.level * Decimal("1.03") else "target_after_liquidity"
        return "aligned"
    if upside.level is not None and _distance_between_pct(stop_loss, upside.level) <= danger_distance:
        return "stop_too_close_to_liquidity"
    if downside.level is None:
        return "needs_review"
    if take_profit > downside.level and _distance_between_pct(take_profit, downside.level) > danger_distance:
        return "target_before_liquidity"
    if take_profit <= downside.level:
        return "aligned" if take_profit >= downside.level * Decimal("0.97") else "target_after_liquidity"
    return "aligned"


def _buffer_pct(*, price: Decimal, candles: Sequence[Candle], atr: Decimal | None) -> Decimal:
    if atr is not None and price > Decimal("0"):
        return max(Decimal("0.20"), min(Decimal("1.50"), (atr / price) * Decimal("100")))
    ranges = [candle.high - candle.low for candle in candles[-14:] if candle.high >= candle.low]
    if not ranges:
        return Decimal("0.50")
    avg_range = sum(ranges, Decimal("0")) / Decimal(len(ranges))
    return max(Decimal("0.20"), min(Decimal("1.50"), (avg_range / price) * Decimal("100")))


def _range_compressed(candles: Sequence[Candle]) -> bool:
    if len(candles) < 24:
        return False
    recent = _average_range(candles[-12:])
    prior = _average_range(candles[-24:-12])
    return prior > Decimal("0") and recent <= prior * Decimal("0.70")


def _average_range(candles: Sequence[Candle]) -> Decimal:
    if not candles:
        return Decimal("0")
    return sum((candle.high - candle.low for candle in candles), Decimal("0")) / Decimal(len(candles))


def _swing_highs(candles: Sequence[Candle]) -> list[Decimal]:
    return [
        candles[index].high
        for index in range(1, len(candles) - 1)
        if candles[index].high >= candles[index - 1].high and candles[index].high >= candles[index + 1].high
    ]


def _swing_lows(candles: Sequence[Candle]) -> list[Decimal]:
    return [
        candles[index].low
        for index in range(1, len(candles) - 1)
        if candles[index].low <= candles[index - 1].low and candles[index].low <= candles[index + 1].low
    ]


def _cluster_count(levels: Sequence[Decimal], target: Decimal, buffer_pct: Decimal) -> int:
    return sum(1 for level in levels if _within_pct(level, target, max(buffer_pct, Decimal("0.25"))))


def _within_pct(left: Decimal, right: Decimal, pct: Decimal) -> bool:
    return _distance_between_pct(left, right) <= pct


def _distance_between_pct(left: Decimal, right: Decimal) -> Decimal:
    base = max(abs(left), abs(right), Decimal("0.00000001"))
    return (abs(left - right) / base) * Decimal("100")


def _distance_pct(*, price: Decimal, level: Decimal | None) -> Decimal | None:
    if level is None or price <= Decimal("0"):
        return None
    return ((abs(level - price) / price) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _strength(*, equal_count: int, swing_count: int, is_range_extreme: bool) -> ZoneStrength:
    score = 1 if is_range_extreme else 0
    score += min(equal_count, 4)
    score += min(swing_count, 3)
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _rounded_level(level: Decimal) -> Decimal:
    return level.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _validated_zone(zone: LiquidityZone) -> LiquidityZone:
    reason = zone.reason
    if "validated by recent liquidation events" not in reason:
        reason = f"{reason}; validated by recent liquidation events"
    return replace(zone, strength="high", reason=reason)


def _validated_nearest_target(
    *,
    zones: LiquidityZoneSnapshot,
    direction: TargetDirection,
    zone: LiquidityZone,
) -> NearestLiquidityTarget:
    if zones.nearest_liquidity_target.direction == direction:
        return replace(zones.nearest_liquidity_target, strength="high")
    return NearestLiquidityTarget(
        direction=direction,
        level=zone.level,
        distance_pct=None,
        strength="high",
    )


def _explanation(
    *,
    upside: LiquidityZone,
    downside: LiquidityZone,
    nearest: NearestLiquidityTarget,
    sweep_risk: SweepRisk,
    alignment: TpSlAlignment,
) -> str:
    target = (
        f"nearest estimated target is {nearest.direction} near {nearest.level}"
        if nearest.level is not None
        else "no clear nearest target is available"
    )
    return (
        f"Estimated liquidity zones only: upside {upside.strength} near {upside.level}, "
        f"downside {downside.strength} near {downside.level}; {target}. "
        f"Sweep risk is {sweep_risk}; TP/SL alignment is {alignment}."
    )
