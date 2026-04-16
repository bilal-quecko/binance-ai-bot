"""Paper execution handoff engine."""

from dataclasses import replace
from decimal import Decimal

from app.paper.broker import PaperBroker
from app.paper.models import FillResult, OrderRequest
from app.risk.models import RiskDecision


class ExecutionEngine:
    """Forward approved paper orders to the in-memory paper broker."""

    def __init__(self, broker: PaperBroker) -> None:
        self._broker = broker

    def execute(self, order: OrderRequest, risk_decision: RiskDecision) -> FillResult:
        """Execute only approved or resized paper orders."""

        if order.mode != "paper":
            return FillResult(
                order_id="REJECTED",
                status="rejected",
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.quantity,
                filled_quantity=Decimal("0"),
                fill_price=order.market_price,
                fee_paid=Decimal("0"),
                realized_pnl=Decimal("0"),
                quote_balance=self._broker.get_balance(order.quote_asset),
                reason_codes=("PAPER_ONLY",),
                position=self._broker.get_position(order.symbol),
            )

        if risk_decision.decision not in {"approve", "resize"}:
            return FillResult(
                order_id="REJECTED",
                status="rejected",
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.quantity,
                filled_quantity=Decimal("0"),
                fill_price=order.market_price,
                fee_paid=Decimal("0"),
                realized_pnl=Decimal("0"),
                quote_balance=self._broker.get_balance(order.quote_asset),
                reason_codes=risk_decision.reason_codes or ("RISK_REJECTED",),
                position=self._broker.get_position(order.symbol),
            )

        approved_quantity = risk_decision.approved_quantity
        if approved_quantity <= Decimal("0"):
            return FillResult(
                order_id="REJECTED",
                status="rejected",
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.quantity,
                filled_quantity=Decimal("0"),
                fill_price=order.market_price,
                fee_paid=Decimal("0"),
                realized_pnl=Decimal("0"),
                quote_balance=self._broker.get_balance(order.quote_asset),
                reason_codes=("INVALID_APPROVED_QUANTITY",),
                position=self._broker.get_position(order.symbol),
            )

        executable_order = replace(order, quantity=approved_quantity)
        return self._broker.execute_order(executable_order)
