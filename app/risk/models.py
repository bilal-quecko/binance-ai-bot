"""Risk models."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.strategies.models import StrategySignal


@dataclass(slots=True)
class RiskInput:
    """Typed context required for deterministic risk evaluation."""

    signal: StrategySignal
    entry_price: Decimal
    requested_quantity: Decimal
    equity: Decimal
    day_start_equity: Decimal
    daily_pnl: Decimal
    open_positions: int
    current_position_quantity: Decimal = Decimal("0")
    stop_price: Decimal | None = None
    volatility: Decimal | None = None
    expected_edge_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal = Decimal("0")
    min_expected_edge_buffer_pct: Decimal = Decimal("0")
    risk_per_trade: Decimal = Decimal("0.005")
    max_daily_loss: Decimal = Decimal("0.02")
    max_open_positions: int = 3
    min_stop_distance_ratio: Decimal = Decimal("0.001")
    quantity_step: Decimal = Decimal("0.00000001")
    mode: Literal["paper", "live"] = "paper"


@dataclass(slots=True)
class RiskDecision:
    """Deterministic outcome of risk evaluation."""

    decision: Literal["approve", "reject", "resize"]
    approved_quantity: Decimal
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    expected_edge_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal | None = None

    @property
    def approved(self) -> bool:
        """Return whether the trade remains allowed after risk checks."""

        return self.decision != "reject"

    @property
    def reason(self) -> str:
        """Return the primary reason code for compatibility with older checks."""

        return self.reason_codes[0] if self.reason_codes else "ok"
