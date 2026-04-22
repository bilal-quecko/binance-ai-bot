"""Support and resistance extraction helpers."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.market_data.candles import Candle


def extract_support_levels(
    candles: Sequence[Candle],
    *,
    current_price: Decimal,
    window: int = 2,
    max_levels: int = 3,
) -> list[Decimal]:
    """Return recent support levels below the current price."""

    return _extract_levels(
        candles,
        current_price=current_price,
        direction="support",
        window=window,
        max_levels=max_levels,
    )


def extract_resistance_levels(
    candles: Sequence[Candle],
    *,
    current_price: Decimal,
    window: int = 2,
    max_levels: int = 3,
) -> list[Decimal]:
    """Return recent resistance levels above the current price."""

    return _extract_levels(
        candles,
        current_price=current_price,
        direction="resistance",
        window=window,
        max_levels=max_levels,
    )


def _extract_levels(
    candles: Sequence[Candle],
    *,
    current_price: Decimal,
    direction: str,
    window: int,
    max_levels: int,
) -> list[Decimal]:
    """Return de-duplicated swing levels for one direction."""

    if len(candles) < (window * 2) + 1:
        return []

    raw_levels: list[Decimal] = []
    for index in range(window, len(candles) - window):
        center = candles[index]
        left = candles[index - window : index]
        right = candles[index + 1 : index + 1 + window]
        if direction == "support":
            candidate = center.low
            neighbors = list(left + right)
            if all(candidate <= candle.low for candle in neighbors) and any(
                candidate < candle.low for candle in neighbors
            ):
                raw_levels.append(candidate)
        else:
            candidate = center.high
            neighbors = list(left + right)
            if all(candidate >= candle.high for candle in neighbors) and any(
                candidate > candle.high for candle in neighbors
            ):
                raw_levels.append(candidate)

    filtered = [
        level
        for level in raw_levels
        if (level < current_price if direction == "support" else level > current_price)
    ]
    if not filtered:
        return []

    tolerance = current_price * Decimal("0.003")
    unique_levels: list[Decimal] = []
    for level in sorted(
        filtered,
        key=lambda item: abs(current_price - item),
    ):
        if any(abs(level - existing) <= tolerance for existing in unique_levels):
            continue
        unique_levels.append(level)
        if len(unique_levels) >= max_levels:
            break

    return sorted(unique_levels)
