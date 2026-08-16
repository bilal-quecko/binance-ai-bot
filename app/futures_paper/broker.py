"""Paper-only Futures broker."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.futures_paper.models import FuturesFillResult, FuturesOrderRequest, FuturesPosition


class FuturesPaperBroker:
    """Paper Futures broker with isolated margin accounting."""

    def __init__(self, *, fee_rate: Decimal = Decimal("0.0004")) -> None:
        self.fee_rate = fee_rate
        self._positions: dict[str, FuturesPosition] = {}
        self.realized_pnl: Decimal = Decimal("0")

    def load_positions(self, positions: list[FuturesPosition]) -> None:
        """Load persisted positions into broker memory."""

        self._positions = {position.symbol.upper(): position for position in positions}

    def positions(self) -> dict[str, FuturesPosition]:
        """Return current paper Futures positions."""

        return dict(self._positions)

    def get_position(self, symbol: str) -> FuturesPosition | None:
        """Return current position for symbol."""

        return self._positions.get(symbol.upper())

    def mark_position(self, symbol: str, mark_price: Decimal) -> FuturesPosition | None:
        """Update one position to the latest mark price."""

        position = self.get_position(symbol)
        if position is None:
            return None
        updated = self._with_mark(position, mark_price, datetime.now(UTC))
        self._positions[position.symbol] = updated
        return updated

    def execute(self, order: FuturesOrderRequest, *, approved: bool, reason_codes: tuple[str, ...]) -> FuturesFillResult:
        """Execute a paper Futures request."""

        order_id = f"fut-paper-{uuid4().hex}"
        symbol = order.symbol.upper()
        if not approved:
            return FuturesFillResult(
                order_id=order_id,
                status="rejected",
                symbol=symbol,
                side=order.side,
                filled_quantity=Decimal("0"),
                fill_price=order.market_price,
                fee_paid=Decimal("0"),
                realized_pnl=Decimal("0"),
                reason_codes=reason_codes,
            )
        if order.side == "CLOSE":
            return self._close(order, order_id, reason_codes)
        return self._open(order, order_id, reason_codes)

    def _open(
        self,
        order: FuturesOrderRequest,
        order_id: str,
        reason_codes: tuple[str, ...],
    ) -> FuturesFillResult:
        now = datetime.now(UTC)
        symbol = order.symbol.upper()
        notional = order.quantity * order.market_price
        fee = notional * self.fee_rate
        position = FuturesPosition(
            symbol=symbol,
            side=order.side,  # type: ignore[arg-type]
            quantity=order.quantity,
            entry_price=order.market_price,
            mark_price=order.market_price,
            leverage=order.leverage,
            margin_mode="isolated",
            margin_used=notional / Decimal(order.leverage),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0") - fee,
            liquidation_price_estimate=self._liquidation_estimate(order.side, order.market_price, order.leverage),
            opened_at=now,
            updated_at=now,
        )
        self._positions[symbol] = position
        self.realized_pnl -= fee
        return FuturesFillResult(
            order_id=order_id,
            status="executed",
            symbol=symbol,
            side=order.side,
            filled_quantity=order.quantity,
            fill_price=order.market_price,
            fee_paid=fee,
            realized_pnl=Decimal("0") - fee,
            reason_codes=reason_codes,
        )

    def _close(
        self,
        order: FuturesOrderRequest,
        order_id: str,
        reason_codes: tuple[str, ...],
    ) -> FuturesFillResult:
        symbol = order.symbol.upper()
        position = self._positions.get(symbol)
        if position is None:
            return FuturesFillResult(
                order_id=order_id,
                status="rejected",
                symbol=symbol,
                side=order.side,
                filled_quantity=Decimal("0"),
                fill_price=order.market_price,
                fee_paid=Decimal("0"),
                realized_pnl=Decimal("0"),
                reason_codes=("NO_POSITION_TO_EXIT",),
            )
        gross = (
            (order.market_price - position.entry_price) * position.quantity
            if position.side == "LONG"
            else (position.entry_price - order.market_price) * position.quantity
        )
        fee = order.market_price * position.quantity * self.fee_rate
        realized = gross - fee
        self.realized_pnl += realized
        del self._positions[symbol]
        return FuturesFillResult(
            order_id=order_id,
            status="executed",
            symbol=symbol,
            side="CLOSE",
            filled_quantity=position.quantity,
            fill_price=order.market_price,
            fee_paid=fee,
            realized_pnl=realized,
            reason_codes=reason_codes,
        )

    def _with_mark(self, position: FuturesPosition, mark_price: Decimal, updated_at: datetime) -> FuturesPosition:
        unrealized = (
            (mark_price - position.entry_price) * position.quantity
            if position.side == "LONG"
            else (position.entry_price - mark_price) * position.quantity
        )
        return FuturesPosition(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            mark_price=mark_price,
            leverage=position.leverage,
            margin_mode=position.margin_mode,
            margin_used=position.margin_used,
            unrealized_pnl=unrealized,
            realized_pnl=position.realized_pnl,
            liquidation_price_estimate=position.liquidation_price_estimate,
            opened_at=position.opened_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _liquidation_estimate(side: str, entry_price: Decimal, leverage: int) -> Decimal:
        buffer = (Decimal("1") / Decimal(leverage)) * Decimal("0.85")
        if side == "SHORT":
            return entry_price * (Decimal("1") + buffer)
        return entry_price * (Decimal("1") - buffer)
