"""Display-only leverage simulation helpers for paper futures scanner candidates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal


LeverageRiskLabel = Literal["low", "medium", "high", "extreme"]
FuturesSimDirection = Literal["long", "short"]
DEFAULT_FEE_SLIPPAGE_PCT = Decimal("0.12")
LEVERAGE_OPTIONS = (1, 2, 3, 5, 10, 25, 50, 100)


@dataclass(slots=True)
class FuturesLeverageSimulation:
    """Paper-only leverage simulation values for scanner display."""

    selected_leverage: int
    estimated_tp_return_percent: Decimal | None
    estimated_sl_return_percent: Decimal | None
    estimated_current_unrealized_return_percent: Decimal | None
    fee_adjusted_tp_return_percent: Decimal | None
    fee_adjusted_sl_return_percent: Decimal | None
    liquidation_risk_label: LeverageRiskLabel
    leverage_warning: str | None
    fee_slippage_estimated: bool


def simulate_futures_leverage(
    *,
    direction: FuturesSimDirection,
    entry_price: Decimal | None,
    take_profit: Decimal | None,
    stop_loss: Decimal | None,
    live_price: Decimal | None,
    leverage: int,
    fee_slippage_pct: Decimal | None = None,
) -> FuturesLeverageSimulation:
    """Calculate display-only paper leverage risk without changing scanner scores."""

    selected_leverage = leverage if leverage in LEVERAGE_OPTIONS else 5
    fee_pct = fee_slippage_pct if fee_slippage_pct is not None else DEFAULT_FEE_SLIPPAGE_PCT
    estimated_fee = fee_slippage_pct is None
    fee_drag = fee_pct * Decimal(selected_leverage)

    tp_return = _leveraged_return(
        direction=direction,
        entry_price=entry_price,
        target_price=take_profit,
        leverage=selected_leverage,
    )
    sl_return = _leveraged_return(
        direction=direction,
        entry_price=entry_price,
        target_price=stop_loss,
        leverage=selected_leverage,
    )
    live_return = _leveraged_return(
        direction=direction,
        entry_price=entry_price,
        target_price=live_price,
        leverage=selected_leverage,
    )
    risk_label = _risk_label(sl_return)
    return FuturesLeverageSimulation(
        selected_leverage=selected_leverage,
        estimated_tp_return_percent=tp_return,
        estimated_sl_return_percent=sl_return,
        estimated_current_unrealized_return_percent=live_return,
        fee_adjusted_tp_return_percent=_subtract_fee(tp_return, fee_drag),
        fee_adjusted_sl_return_percent=_subtract_fee(sl_return, fee_drag),
        liquidation_risk_label=risk_label,
        leverage_warning=_leverage_warning(selected_leverage),
        fee_slippage_estimated=estimated_fee,
    )


def _leveraged_return(
    *,
    direction: FuturesSimDirection,
    entry_price: Decimal | None,
    target_price: Decimal | None,
    leverage: int,
) -> Decimal | None:
    if entry_price is None or target_price is None or entry_price <= Decimal("0"):
        return None
    if direction == "long":
        raw = ((target_price - entry_price) / entry_price) * Decimal("100") * Decimal(leverage)
    else:
        raw = ((entry_price - target_price) / entry_price) * Decimal("100") * Decimal(leverage)
    return raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _subtract_fee(value: Decimal | None, fee_drag: Decimal) -> Decimal | None:
    if value is None:
        return None
    return (value - fee_drag).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _risk_label(stop_loss_return: Decimal | None) -> LeverageRiskLabel:
    if stop_loss_return is None:
        return "high"
    impact = abs(stop_loss_return)
    if impact < Decimal("5"):
        return "low"
    if impact < Decimal("15"):
        return "medium"
    if impact < Decimal("50"):
        return "high"
    return "extreme"


def _leverage_warning(leverage: int) -> str | None:
    if leverage >= 50:
        return "Extreme paper leverage. Small adverse moves can wipe out simulated margin."
    if leverage >= 25:
        return "High paper leverage. Adverse moves and fee drag can dominate the simulated setup."
    return None
