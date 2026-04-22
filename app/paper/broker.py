"""In-memory paper broker."""

from dataclasses import replace
from decimal import Decimal

from app.paper.models import FillResult, OrderRequest, Position


class PaperBroker:
    """Execute paper trades against in-memory balances and positions."""

    def __init__(
        self,
        *,
        initial_balances: dict[str, Decimal] | None = None,
        initial_positions: dict[str, Position] | None = None,
        initial_realized_pnl: Decimal = Decimal("0"),
        fee_rate: Decimal = Decimal("0.001"),
        slippage_pct: Decimal = Decimal("0"),
    ) -> None:
        self._balances: dict[str, Decimal] = dict(initial_balances or {"USDT": Decimal("10000")})
        self._positions: dict[str, Position] = {
            symbol.upper(): replace(position)
            for symbol, position in (initial_positions or {}).items()
        }
        self._fee_rate = fee_rate
        self._slippage_pct = slippage_pct
        self._order_counter = 0
        self._realized_pnl = initial_realized_pnl

    @property
    def realized_pnl(self) -> Decimal:
        """Return cumulative realized PnL across closed paper trades."""

        return self._realized_pnl

    @property
    def fee_rate(self) -> Decimal:
        """Return the configured paper fee rate."""

        return self._fee_rate

    @property
    def slippage_pct(self) -> Decimal:
        """Return the configured paper slippage percentage."""

        return self._slippage_pct

    def balances(self) -> dict[str, Decimal]:
        """Return a copy of the current in-memory balances."""

        return dict(self._balances)

    def positions(self) -> dict[str, Position]:
        """Return copies of the current in-memory positions."""

        return {symbol: replace(position) for symbol, position in self._positions.items()}

    def get_balance(self, asset: str) -> Decimal:
        """Return the current balance for an asset."""

        return self._balances.get(asset.upper(), Decimal("0"))

    def get_position(self, symbol: str) -> Position | None:
        """Return a copy of the current position for a symbol."""

        position = self._positions.get(symbol.upper())
        return replace(position) if position is not None else None

    def _next_order_id(self) -> str:
        """Return a deterministic paper order id."""

        self._order_counter += 1
        return f"PAPER-{self._order_counter:06d}"

    def _reject(
        self,
        order: OrderRequest,
        *reason_codes: str,
    ) -> FillResult:
        """Return a rejected paper fill result."""

        return FillResult(
            order_id=self._next_order_id(),
            status="rejected",
            symbol=order.symbol,
            side=order.side,
            requested_quantity=order.quantity,
            filled_quantity=Decimal("0"),
            fill_price=order.market_price,
            fee_paid=Decimal("0"),
            realized_pnl=Decimal("0"),
            quote_balance=self.get_balance(order.quote_asset),
            reason_codes=tuple(reason_codes),
            position=self.get_position(order.symbol),
        )

    def _fill_price(self, order: OrderRequest) -> Decimal:
        """Return the slipped execution price for the paper fill."""

        if order.side == "BUY":
            return order.market_price * (Decimal("1") + self._slippage_pct)
        return order.market_price * (Decimal("1") - self._slippage_pct)

    def execute_order(self, order: OrderRequest) -> FillResult:
        """Execute a paper order against in-memory balances and positions."""

        if order.mode != "paper":
            return self._reject(order, "PAPER_ONLY")
        if order.quantity <= Decimal("0") or order.market_price <= Decimal("0"):
            return self._reject(order, "INVALID_ORDER")

        symbol = order.symbol.upper()
        quote_asset = order.quote_asset.upper()
        fill_price = self._fill_price(order)
        notional = fill_price * order.quantity
        fee = notional * self._fee_rate

        if order.side == "BUY":
            total_cost = notional + fee
            if self.get_balance(quote_asset) < total_cost:
                return self._reject(order, "INSUFFICIENT_BALANCE")

            self._balances[quote_asset] = self.get_balance(quote_asset) - total_cost
            current = self._positions.get(symbol)
            if current is None:
                new_position = Position(
                    symbol=symbol,
                    quantity=order.quantity,
                    avg_entry_price=total_cost / order.quantity,
                    quote_asset=quote_asset,
                )
            else:
                new_quantity = current.quantity + order.quantity
                new_cost_basis = (current.avg_entry_price * current.quantity) + total_cost
                new_position = Position(
                    symbol=symbol,
                    quantity=new_quantity,
                    avg_entry_price=new_cost_basis / new_quantity,
                    quote_asset=quote_asset,
                    realized_pnl=current.realized_pnl,
                )
            self._positions[symbol] = new_position
            return FillResult(
                order_id=self._next_order_id(),
                status="executed",
                symbol=symbol,
                side=order.side,
                requested_quantity=order.quantity,
                filled_quantity=order.quantity,
                fill_price=fill_price,
                fee_paid=fee,
                realized_pnl=Decimal("0"),
                quote_balance=self.get_balance(quote_asset),
                reason_codes=("EXECUTED",),
                position=replace(new_position),
            )

        current = self._positions.get(symbol)
        if current is None or current.quantity < order.quantity:
            return self._reject(order, "INSUFFICIENT_POSITION")

        net_proceeds = notional - fee
        realized_pnl = net_proceeds - (current.avg_entry_price * order.quantity)
        self._balances[quote_asset] = self.get_balance(quote_asset) + net_proceeds
        self._realized_pnl += realized_pnl

        remaining_quantity = current.quantity - order.quantity
        updated_position: Position | None
        if remaining_quantity == Decimal("0"):
            updated_position = None
            del self._positions[symbol]
        else:
            updated_position = Position(
                symbol=symbol,
                quantity=remaining_quantity,
                avg_entry_price=current.avg_entry_price,
                quote_asset=quote_asset,
                realized_pnl=current.realized_pnl + realized_pnl,
            )
            self._positions[symbol] = updated_position

        return FillResult(
            order_id=self._next_order_id(),
            status="executed",
            symbol=symbol,
            side=order.side,
            requested_quantity=order.quantity,
            filled_quantity=order.quantity,
            fill_price=fill_price,
            fee_paid=fee,
            realized_pnl=realized_pnl,
            quote_balance=self.get_balance(quote_asset),
            reason_codes=("EXECUTED",),
            position=replace(updated_position) if updated_position is not None else None,
        )
