"""Deterministic position sizing helpers."""

from decimal import Decimal, ROUND_DOWN


def fixed_fraction_risk_amount(equity: Decimal, risk_per_trade: Decimal) -> Decimal:
    """Return the maximum risk capital for a single trade."""

    if equity <= Decimal("0"):
        raise ValueError("equity must be positive")
    if risk_per_trade <= Decimal("0"):
        raise ValueError("risk_per_trade must be positive")
    return equity * risk_per_trade


def floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    """Round quantity down to the nearest valid step."""

    if step <= Decimal("0"):
        raise ValueError("step must be positive")
    return quantity.quantize(step, rounding=ROUND_DOWN)


def size_for_risk(
    *,
    equity: Decimal,
    risk_per_trade: Decimal,
    risk_distance: Decimal,
    quantity_step: Decimal,
) -> Decimal:
    """Return the deterministic position size allowed by risk constraints."""

    if risk_distance <= Decimal("0"):
        raise ValueError("risk_distance must be positive")

    raw_quantity = fixed_fraction_risk_amount(equity, risk_per_trade) / risk_distance
    return floor_to_step(raw_quantity, quantity_step)
