"""Range-behavior calculations for multi-horizon pattern analysis."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
import math

from app.analysis.pattern_summary import (
    BreakoutTendency,
    PatternDirection,
    PatternPricePoint,
    ReversalTendency,
    TrendCharacter,
)


def net_return_pct(points: Sequence[PatternPricePoint]) -> Decimal | None:
    """Return the net return over the selected horizon."""

    if len(points) < 2 or points[0].close_price <= Decimal("0"):
        return None
    return ((points[-1].close_price - points[0].close_price) / points[0].close_price) * Decimal("100")


def overall_direction(points: Sequence[PatternPricePoint]) -> PatternDirection | None:
    """Classify the horizon direction from net return."""

    horizon_return = net_return_pct(points)
    if horizon_return is None:
        return None
    if horizon_return >= Decimal("1.0"):
        return "bullish"
    if horizon_return <= Decimal("-1.0"):
        return "bearish"
    return "sideways"


def move_counts(points: Sequence[PatternPricePoint]) -> tuple[int, int, int]:
    """Return counts of up, down, and flat close-to-close moves."""

    up_moves = 0
    down_moves = 0
    flat_moves = 0
    for previous, current in zip(points, points[1:]):
        if current.close_price > previous.close_price:
            up_moves += 1
        elif current.close_price < previous.close_price:
            down_moves += 1
        else:
            flat_moves += 1
    return (up_moves, down_moves, flat_moves)


def move_ratio_pct(count: int, total_moves: int) -> Decimal | None:
    """Return one move count as a percentage of total moves."""

    if total_moves <= 0:
        return None
    return (Decimal(count) / Decimal(total_moves)) * Decimal("100")


def realized_volatility_pct(points: Sequence[PatternPricePoint]) -> Decimal | None:
    """Return realized volatility from close-to-close percentage returns."""

    returns = _returns(points)
    if len(returns) < 2:
        return None
    mean = sum(returns, start=Decimal("0")) / Decimal(len(returns))
    variance = sum((value - mean) ** 2 for value in returns) / Decimal(len(returns))
    stddev = Decimal(str(math.sqrt(float(variance))))
    return stddev * Decimal("100")


def max_drawdown_pct(points: Sequence[PatternPricePoint]) -> Decimal | None:
    """Return max drawdown percentage over the horizon."""

    if not points:
        return None
    peak = points[0].close_price
    max_drawdown = Decimal("0")
    for point in points:
        peak = max(peak, point.close_price)
        if peak <= Decimal("0"):
            continue
        drawdown = ((peak - point.close_price) / peak) * Decimal("100")
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def trend_character(points: Sequence[PatternPricePoint]) -> TrendCharacter | None:
    """Classify whether the horizon behavior is persistent or choppy."""

    returns = _returns(points)
    if not returns:
        return None
    same_direction_pairs = 0
    directional_pairs = 0
    previous_sign = 0
    for value in returns:
        sign = 1 if value > Decimal("0") else -1 if value < Decimal("0") else 0
        if sign == 0:
            continue
        if previous_sign != 0:
            directional_pairs += 1
            if previous_sign == sign:
                same_direction_pairs += 1
        previous_sign = sign
    if directional_pairs == 0:
        return "balanced"
    persistence_ratio = Decimal(same_direction_pairs) / Decimal(directional_pairs)
    if persistence_ratio >= Decimal("0.65"):
        return "persistent"
    if persistence_ratio <= Decimal("0.4"):
        return "choppy"
    return "balanced"


def breakout_tendency(
    *,
    direction: PatternDirection | None,
    horizon_return_pct: Decimal | None,
    volatility_pct: Decimal | None,
    drawdown_pct: Decimal | None,
) -> BreakoutTendency | None:
    """Classify whether the horizon behaved more like a breakout or a range."""

    if direction is None or horizon_return_pct is None or volatility_pct is None or drawdown_pct is None:
        return None
    abs_return = abs(horizon_return_pct)
    if direction in {"bullish", "bearish"} and abs_return >= Decimal("3") and drawdown_pct <= Decimal("4"):
        return "breakout_prone"
    if abs_return <= Decimal("1.5") and volatility_pct <= Decimal("1.2"):
        return "range_bound"
    return "mixed"


def reversal_tendency(
    *,
    direction: PatternDirection | None,
    horizon_return_pct: Decimal | None,
    drawdown_pct: Decimal | None,
    trend_state: TrendCharacter | None,
) -> ReversalTendency | None:
    """Estimate whether the horizon shows meaningful reversal risk."""

    if direction is None or horizon_return_pct is None or drawdown_pct is None or trend_state is None:
        return None
    abs_return = abs(horizon_return_pct)
    if trend_state == "choppy":
        return "elevated"
    if abs_return >= Decimal("5") and drawdown_pct >= Decimal("3"):
        return "elevated"
    if trend_state == "persistent" and drawdown_pct <= Decimal("1.5"):
        return "low"
    return "normal"


def _returns(points: Sequence[PatternPricePoint]) -> list[Decimal]:
    """Return close-to-close percentage returns as fractions."""

    returns: list[Decimal] = []
    for previous, current in zip(points, points[1:]):
        if previous.close_price <= Decimal("0"):
            continue
        returns.append((current.close_price - previous.close_price) / previous.close_price)
    return returns
