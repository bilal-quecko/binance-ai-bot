"""Performance analytics helpers for paper-mode monitoring."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.storage.models import DrawdownSummary, PnlSnapshotRecord, TradeRecord


@dataclass(slots=True)
class PerformanceAnalytics:
    """Deterministic performance analytics for closed paper trades."""

    total_closed_trades: int
    expectancy_per_closed_trade: Decimal | None
    profit_factor: Decimal | None
    average_hold_seconds: int | None
    average_win: Decimal | None
    average_loss: Decimal | None
    session_realized_pnl: Decimal
    session_unrealized_pnl: Decimal
    symbol_realized_pnl: Decimal
    max_drawdown: Decimal
    current_drawdown: Decimal


@dataclass(slots=True)
class _OpenLot:
    """One open buy lot used for hold-time matching."""

    entry_time: datetime
    quantity_remaining: Decimal


def _start_of_day(value: date) -> datetime:
    """Return the UTC start datetime for a date filter."""

    return datetime.combine(value, time.min, tzinfo=UTC)


def _next_day(value: date) -> datetime:
    """Return the UTC start datetime for the next date."""

    return _start_of_day(value) + timedelta(days=1)


def _trade_in_range(
    trade: TradeRecord,
    *,
    start_date: date | None,
    end_date: date | None,
) -> bool:
    """Return whether a trade timestamp falls inside the requested date range."""

    if start_date is not None and trade.event_time < _start_of_day(start_date):
        return False
    if end_date is not None and trade.event_time >= _next_day(end_date):
        return False
    return True


def _to_optional_decimal(value: Decimal, count: int) -> Decimal | None:
    """Return an average value only when the divisor is non-zero."""

    if count <= 0:
        return None
    return value / Decimal(count)


def _quantized_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Return a ratio rounded for display, or ``None`` when undefined."""

    if denominator == Decimal("0"):
        return None
    return (numerator / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def build_performance_analytics(
    *,
    trades: list[TradeRecord],
    latest_pnl: PnlSnapshotRecord | None,
    drawdown: DrawdownSummary,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PerformanceAnalytics:
    """Build closed-trade performance analytics from persisted paper-mode data."""

    open_lots: deque[_OpenLot] = deque()
    closed_trades: list[TradeRecord] = []
    hold_seconds_total = Decimal("0")
    matched_quantity_total = Decimal("0")

    for trade in trades:
        if trade.status != "executed":
            continue

        if trade.side == "BUY":
            open_lots.append(_OpenLot(entry_time=trade.event_time, quantity_remaining=trade.filled_quantity))
            continue

        if trade.side != "SELL":
            continue

        quantity_remaining = trade.filled_quantity
        sell_hold_seconds = Decimal("0")
        sell_matched_quantity = Decimal("0")
        while quantity_remaining > Decimal("0") and open_lots:
            lot = open_lots[0]
            matched_quantity = min(lot.quantity_remaining, quantity_remaining)
            hold_seconds = Decimal((trade.event_time - lot.entry_time).total_seconds())
            sell_hold_seconds += hold_seconds * matched_quantity
            sell_matched_quantity += matched_quantity
            lot.quantity_remaining -= matched_quantity
            quantity_remaining -= matched_quantity
            if lot.quantity_remaining <= Decimal("0"):
                open_lots.popleft()

        if not _trade_in_range(trade, start_date=start_date, end_date=end_date):
            continue

        closed_trades.append(trade)
        hold_seconds_total += sell_hold_seconds
        matched_quantity_total += sell_matched_quantity

    gross_profit = sum(
        trade.realized_pnl
        for trade in closed_trades
        if trade.realized_pnl > Decimal("0")
    )
    gross_loss = sum(
        abs(trade.realized_pnl)
        for trade in closed_trades
        if trade.realized_pnl < Decimal("0")
    )
    winning_trades = sum(1 for trade in closed_trades if trade.realized_pnl > Decimal("0"))
    losing_trades = sum(1 for trade in closed_trades if trade.realized_pnl < Decimal("0"))
    realized_pnl_sum = sum((trade.realized_pnl for trade in closed_trades), start=Decimal("0"))

    average_hold_seconds: int | None = None
    if matched_quantity_total > Decimal("0"):
        average_hold_seconds = int(
            (hold_seconds_total / matched_quantity_total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    session_realized_pnl = latest_pnl.realized_pnl if latest_pnl is not None else Decimal("0")
    session_total_pnl = latest_pnl.total_pnl if latest_pnl is not None else Decimal("0")
    symbol_realized_pnl = realized_pnl_sum

    return PerformanceAnalytics(
        total_closed_trades=len(closed_trades),
        expectancy_per_closed_trade=_to_optional_decimal(realized_pnl_sum, len(closed_trades)),
        profit_factor=_quantized_ratio(gross_profit, gross_loss),
        average_hold_seconds=average_hold_seconds,
        average_win=_to_optional_decimal(gross_profit, winning_trades),
        average_loss=(
            -(gross_loss / Decimal(losing_trades))
            if losing_trades > 0
            else None
        ),
        session_realized_pnl=session_realized_pnl,
        session_unrealized_pnl=session_total_pnl - session_realized_pnl,
        symbol_realized_pnl=symbol_realized_pnl,
        max_drawdown=drawdown.max_drawdown,
        current_drawdown=drawdown.current_drawdown,
    )
