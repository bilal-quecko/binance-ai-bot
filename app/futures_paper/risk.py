"""Deterministic paper Futures risk checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.futures_paper.models import FuturesOrderRequest, FuturesPosition


@dataclass(slots=True)
class FuturesRiskDecision:
    """Paper Futures risk decision."""

    approved: bool
    reason_codes: tuple[str, ...]
    leverage: int


class FuturesPaperRiskEngine:
    """Conservative deterministic Futures paper risk gate."""

    def __init__(
        self,
        *,
        default_leverage: int = 2,
        max_leverage: int = 3,
        min_liquidation_distance_pct: Decimal = Decimal("12"),
        max_positions: int = 3,
    ) -> None:
        self.default_leverage = default_leverage
        self.max_leverage = max_leverage
        self.min_liquidation_distance_pct = min_liquidation_distance_pct
        self.max_positions = max_positions

    def evaluate(
        self,
        order: FuturesOrderRequest,
        *,
        current_position: FuturesPosition | None,
        open_position_count: int,
        liquidation_distance_pct: Decimal | None = None,
    ) -> FuturesRiskDecision:
        """Evaluate a paper Futures request."""

        if order.mode != "paper":
            return FuturesRiskDecision(False, ("PAPER_ONLY",), self.default_leverage)
        if order.market_price <= Decimal("0") or order.quantity <= Decimal("0"):
            return FuturesRiskDecision(False, ("INVALID_ORDER_REQUEST",), self.default_leverage)
        if order.leverage > self.max_leverage:
            return FuturesRiskDecision(False, ("DANGEROUS_LEVERAGE",), self.max_leverage)
        if order.leverage < 1:
            return FuturesRiskDecision(False, ("INVALID_LEVERAGE",), self.default_leverage)
        if order.side == "CLOSE":
            if current_position is None:
                return FuturesRiskDecision(False, ("NO_POSITION_TO_EXIT",), order.leverage)
            return FuturesRiskDecision(True, ("FUTURES_CLOSE_APPROVED",), order.leverage)
        if current_position is not None:
            return FuturesRiskDecision(False, ("POSITION_ALREADY_OPEN",), order.leverage)
        if open_position_count >= self.max_positions:
            return FuturesRiskDecision(False, ("POSITION_LIMIT",), order.leverage)
        if liquidation_distance_pct is not None and liquidation_distance_pct < self.min_liquidation_distance_pct:
            return FuturesRiskDecision(False, ("LIQUIDATION_RISK_HIGH",), order.leverage)
        return FuturesRiskDecision(True, ("FUTURES_PAPER_APPROVED",), order.leverage)
