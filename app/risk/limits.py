"""Deterministic risk checks and evaluation."""

from decimal import Decimal

from app.risk.models import RiskDecision, RiskInput
from app.risk.position_sizing import size_for_risk


def check_daily_loss(current_drawdown: float | Decimal, max_daily_loss: float | Decimal) -> RiskDecision:
    """Return whether the daily loss limit has been reached."""

    drawdown = Decimal(str(current_drawdown))
    limit = Decimal(str(max_daily_loss))
    if drawdown >= limit:
        return RiskDecision(
            decision="reject",
            approved_quantity=Decimal("0"),
            reason_codes=("daily_loss_limit_reached",),
        )
    return RiskDecision(
        decision="approve",
        approved_quantity=Decimal("0"),
        reason_codes=("ok",),
    )


class RiskEngine:
    """Evaluate strategy signals against deterministic paper-trading risk rules."""

    @staticmethod
    def _reject(*reason_codes: str) -> RiskDecision:
        """Return a rejection decision with zero approved quantity."""

        return RiskDecision(
            decision="reject",
            approved_quantity=Decimal("0"),
            reason_codes=tuple(reason_codes),
        )

    @staticmethod
    def _risk_distance(risk_input: RiskInput) -> Decimal | None:
        """Return the per-unit risk distance used for stop and sizing checks."""

        stop_distance: Decimal | None = None
        if risk_input.stop_price is not None:
            stop_distance = risk_input.entry_price - risk_input.stop_price
            if stop_distance <= Decimal("0"):
                return None

        volatility = risk_input.volatility
        if volatility is not None and volatility <= Decimal("0"):
            return None

        if stop_distance is None:
            return volatility
        if volatility is None:
            return stop_distance
        return max(stop_distance, volatility)

    def evaluate(self, risk_input: RiskInput) -> RiskDecision:
        """Evaluate a strategy signal against deterministic risk constraints."""

        if risk_input.mode != "paper":
            return self._reject("PAPER_ONLY")
        if risk_input.signal.side not in {"BUY", "SELL"}:
            return self._reject("NON_ACTIONABLE_SIGNAL")
        if risk_input.entry_price <= Decimal("0") or risk_input.requested_quantity <= Decimal("0"):
            return self._reject("INVALID_ORDER_REQUEST")
        if risk_input.day_start_equity <= Decimal("0") or risk_input.equity <= Decimal("0"):
            return self._reject("INVALID_EQUITY_CONTEXT")

        if risk_input.signal.side == "SELL":
            if risk_input.current_position_quantity <= Decimal("0"):
                return self._reject("NO_POSITION_TO_EXIT")
            if risk_input.requested_quantity > risk_input.current_position_quantity:
                return RiskDecision(
                    decision="resize",
                    approved_quantity=risk_input.current_position_quantity,
                    reason_codes=("RESIZED_TO_POSITION",),
                )
            return RiskDecision(
                decision="approve",
                approved_quantity=risk_input.requested_quantity,
                reason_codes=("EXIT_APPROVED",),
            )

        current_drawdown = max(-risk_input.daily_pnl, Decimal("0")) / risk_input.day_start_equity
        daily_loss_decision = check_daily_loss(current_drawdown, risk_input.max_daily_loss)
        if not daily_loss_decision.approved:
            return self._reject("DAILY_LOSS_LIMIT")

        if risk_input.open_positions >= risk_input.max_open_positions:
            return self._reject("OPEN_POSITION_LIMIT")

        risk_distance = self._risk_distance(risk_input)
        if risk_distance is None:
            return self._reject("INVALID_STOP_OR_VOLATILITY")

        if risk_distance / risk_input.entry_price < risk_input.min_stop_distance_ratio:
            return self._reject("STOP_DISTANCE_TOO_TIGHT")

        allowed_quantity = size_for_risk(
            equity=risk_input.equity,
            risk_per_trade=risk_input.risk_per_trade,
            risk_distance=risk_distance,
            quantity_step=risk_input.quantity_step,
        )
        if allowed_quantity <= Decimal("0"):
            return self._reject("SIZE_BELOW_MINIMUM")

        if allowed_quantity < risk_input.requested_quantity:
            return RiskDecision(
                decision="resize",
                approved_quantity=allowed_quantity,
                reason_codes=("RESIZED_FOR_RISK",),
            )

        return RiskDecision(
            decision="approve",
            approved_quantity=risk_input.requested_quantity,
            reason_codes=("APPROVED",),
        )
