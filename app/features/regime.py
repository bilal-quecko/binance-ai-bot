"""Regime classification helpers."""

from decimal import Decimal
from typing import Literal


def classify_regime(
    *,
    ema_fast: Decimal | None,
    ema_slow: Decimal | None,
) -> Literal["bullish", "bearish", "neutral"] | None:
    """Classify the market regime from fast and slow EMA values."""

    if ema_fast is None or ema_slow is None:
        return None
    if ema_fast > ema_slow:
        return "bullish"
    if ema_fast < ema_slow:
        return "bearish"
    return "neutral"
