"""Volatility regime helpers for technical analysis."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


VolatilityRegime = Literal["low", "normal", "high", "unknown"]


def classify_volatility_regime(
    *,
    atr: Decimal | None,
    price: Decimal | None,
) -> VolatilityRegime:
    """Classify volatility from ATR as a fraction of price."""

    if atr is None or price is None or price <= Decimal("0"):
        return "unknown"

    atr_ratio = atr / price
    if atr_ratio < Decimal("0.005"):
        return "low"
    if atr_ratio < Decimal("0.015"):
        return "normal"
    return "high"
