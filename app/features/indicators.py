"""Deterministic feature indicators."""

from collections.abc import Sequence
from decimal import Decimal

from app.market_data.candles import Candle


def sma(values: Sequence[Decimal]) -> Decimal:
    """Return the simple moving average for a non-empty decimal series."""

    if not values:
        raise ValueError("values cannot be empty")
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def ema(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Return the exponential moving average for the provided series."""

    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None

    multiplier = Decimal("2") / Decimal(period + 1)
    current = sma(values[:period])
    for value in values[period:]:
        current = ((value - current) * multiplier) + current
    return current


def rsi(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Return the RSI using Wilder smoothing over close prices."""

    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period + 1:
        return None

    changes = [current - previous for previous, current in zip(values, values[1:])]
    gains = [max(change, Decimal("0")) for change in changes]
    losses = [max(-change, Decimal("0")) for change in changes]

    average_gain = sma(gains[:period])
    average_loss = sma(losses[:period])

    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * Decimal(period - 1)) + gain) / Decimal(period)
        average_loss = ((average_loss * Decimal(period - 1)) + loss) / Decimal(period)

    if average_loss == Decimal("0"):
        if average_gain == Decimal("0"):
            return Decimal("50")
        return Decimal("100")

    relative_strength = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))


def atr(candles: Sequence[Candle], period: int) -> Decimal | None:
    """Return the Average True Range using Wilder smoothing."""

    if period <= 0:
        raise ValueError("period must be positive")
    if len(candles) < period:
        return None

    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None

    for candle in candles:
        high_low = candle.high - candle.low
        if previous_close is None:
            true_range = high_low
        else:
            high_close = abs(candle.high - previous_close)
            low_close = abs(candle.low - previous_close)
            true_range = max(high_low, high_close, low_close)
        true_ranges.append(true_range)
        previous_close = candle.close

    current = sma(true_ranges[:period])
    for true_range in true_ranges[period:]:
        current = ((current * Decimal(period - 1)) + true_range) / Decimal(period)
    return current
