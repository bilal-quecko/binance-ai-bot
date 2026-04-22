"""Deterministic trade-quality analytics for closed paper trades."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.storage.models import MarketCandleSnapshotRecord, TradeRecord

_HUNDRED = Decimal("100")
_PERCENT_STEP = Decimal("0.01")


@dataclass(slots=True)
class HoldTimeDistributionSummary:
    """Summary statistics for closed-trade hold times."""

    average_seconds: int | None
    median_seconds: int | None
    p75_seconds: int | None
    max_seconds: int | None


@dataclass(slots=True)
class TradeQualityDetail:
    """Attribution details for one closed paper trade."""

    order_id: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    hold_seconds: int
    mfe_pct: Decimal
    mae_pct: Decimal
    captured_move_pct: Decimal
    giveback_pct: Decimal
    entry_quality_score: Decimal
    exit_quality_score: Decimal


@dataclass(slots=True)
class TradeQualitySummary:
    """Summary metrics for recent closed-trade quality."""

    total_closed_trades: int
    average_mfe_pct: Decimal | None
    average_mae_pct: Decimal | None
    average_captured_move_pct: Decimal | None
    average_giveback_pct: Decimal | None
    average_entry_quality_score: Decimal | None
    average_exit_quality_score: Decimal | None
    longest_no_trade_seconds: int | None
    hold_time_distribution: HoldTimeDistributionSummary


@dataclass(slots=True)
class TradeQualityAnalytics:
    """Trade-quality summary plus recent attribution details."""

    summary: TradeQualitySummary
    details: list[TradeQualityDetail]


@dataclass(slots=True)
class _OpenLot:
    """One open buy lot used for FIFO close attribution."""

    entry_time: datetime
    entry_price: Decimal
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
    """Return whether a trade falls inside the requested date range."""

    if start_date is not None and trade.event_time < _start_of_day(start_date):
        return False
    if end_date is not None and trade.event_time >= _next_day(end_date):
        return False
    return True


def _quantize(value: Decimal) -> Decimal:
    """Round a Decimal percentage/score for stable display."""

    return value.quantize(_PERCENT_STEP, rounding=ROUND_HALF_UP)


def _average_decimal(values: list[Decimal]) -> Decimal | None:
    """Return the arithmetic mean for one or more Decimal values."""

    if not values:
        return None
    return _quantize(sum(values, start=Decimal("0")) / Decimal(len(values)))


def _clamp_pct(value: Decimal) -> Decimal:
    """Clamp a percentage-like value into the inclusive 0..100 range."""

    if value < Decimal("0"):
        return Decimal("0")
    if value > _HUNDRED:
        return _HUNDRED
    return value


def _percentage_change(move: Decimal, baseline: Decimal) -> Decimal:
    """Return percentage move against a positive baseline."""

    if baseline <= Decimal("0"):
        return Decimal("0")
    return _quantize((move / baseline) * _HUNDRED)


def _nearest_rank(values: list[int], percentile: Decimal) -> int | None:
    """Return a nearest-rank percentile from ascending integer values."""

    if not values:
        return None
    rank = int((Decimal(len(values)) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    index = max(0, min(len(values) - 1, rank - 1))
    return values[index]


def _hold_time_distribution(details: list[TradeQualityDetail]) -> HoldTimeDistributionSummary:
    """Build a deterministic hold-time summary from closed-trade details."""

    hold_seconds = sorted(detail.hold_seconds for detail in details)
    if not hold_seconds:
        return HoldTimeDistributionSummary(
            average_seconds=None,
            median_seconds=None,
            p75_seconds=None,
            max_seconds=None,
        )
    average_seconds = int(
        (
            Decimal(sum(hold_seconds)) / Decimal(len(hold_seconds))
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    midpoint = len(hold_seconds) // 2
    if len(hold_seconds) % 2 == 0:
        median_seconds = int(
            (
                Decimal(hold_seconds[midpoint - 1] + hold_seconds[midpoint]) / Decimal("2")
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        median_seconds = hold_seconds[midpoint]
    return HoldTimeDistributionSummary(
        average_seconds=average_seconds,
        median_seconds=median_seconds,
        p75_seconds=_nearest_rank(hold_seconds, Decimal("0.75")),
        max_seconds=hold_seconds[-1],
    )


def _longest_no_trade_seconds(trades: list[TradeRecord], *, start_date: date | None, end_date: date | None) -> int | None:
    """Return the longest idle gap between consecutive executed trades in range."""

    executed = [
        trade
        for trade in trades
        if trade.status == "executed" and _trade_in_range(trade, start_date=start_date, end_date=end_date)
    ]
    if len(executed) < 2:
        return None
    longest = max(
        int((current.event_time - previous.event_time).total_seconds())
        for previous, current in zip(executed, executed[1:], strict=False)
    )
    return longest


def _select_window_prices(
    *,
    candles: list[MarketCandleSnapshotRecord],
    entry_time: datetime,
    exit_time: datetime,
    entry_price: Decimal,
    exit_price: Decimal,
) -> list[Decimal]:
    """Return candle-close prices observed between entry and exit, inclusive."""

    prices = [
        candle.close_price
        for candle in candles
        if candle.close_time >= entry_time and candle.close_time <= exit_time
    ]
    prices.append(entry_price)
    prices.append(exit_price)
    return prices


def build_trade_quality_analytics(
    *,
    trades: list[TradeRecord],
    candles: list[MarketCandleSnapshotRecord],
    start_date: date | None = None,
    end_date: date | None = None,
) -> TradeQualityAnalytics:
    """Build deterministic trade-quality analytics from persisted paper trades."""

    open_lots: deque[_OpenLot] = deque()
    details: list[TradeQualityDetail] = []

    for trade in trades:
        if trade.status != "executed":
            continue

        if trade.side == "BUY":
            open_lots.append(
                _OpenLot(
                    entry_time=trade.event_time,
                    entry_price=trade.fill_price,
                    quantity_remaining=trade.filled_quantity,
                )
            )
            continue

        if trade.side != "SELL":
            continue

        quantity_remaining = trade.filled_quantity
        matched_quantity = Decimal("0")
        weighted_entry_price_total = Decimal("0")
        weighted_hold_seconds_total = Decimal("0")
        first_entry_time = trade.event_time

        while quantity_remaining > Decimal("0") and open_lots:
            lot = open_lots[0]
            matched = min(lot.quantity_remaining, quantity_remaining)
            matched_quantity += matched
            weighted_entry_price_total += lot.entry_price * matched
            weighted_hold_seconds_total += Decimal((trade.event_time - lot.entry_time).total_seconds()) * matched
            first_entry_time = min(first_entry_time, lot.entry_time)
            lot.quantity_remaining -= matched
            quantity_remaining -= matched
            if lot.quantity_remaining <= Decimal("0"):
                open_lots.popleft()

        if matched_quantity <= Decimal("0"):
            continue
        if not _trade_in_range(trade, start_date=start_date, end_date=end_date):
            continue

        entry_price = weighted_entry_price_total / matched_quantity
        hold_seconds = int(
            (weighted_hold_seconds_total / matched_quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        prices = _select_window_prices(
            candles=candles,
            entry_time=first_entry_time,
            exit_time=trade.event_time,
            entry_price=entry_price,
            exit_price=trade.fill_price,
        )
        max_price = max(prices)
        min_price = min(prices)
        price_range = max_price - min_price
        favorable_move = max(max_price - entry_price, Decimal("0"))
        adverse_move = max(entry_price - min_price, Decimal("0"))
        realized_move = max(trade.fill_price - entry_price, Decimal("0"))
        mfe_pct = _percentage_change(favorable_move, entry_price)
        mae_pct = _percentage_change(adverse_move, entry_price)

        if favorable_move > Decimal("0"):
            captured_move_pct = _quantize(
                _clamp_pct((realized_move / favorable_move) * _HUNDRED)
            )
            giveback_pct = _quantize(
                _clamp_pct(((max_price - trade.fill_price) / favorable_move) * _HUNDRED)
            )
        else:
            captured_move_pct = Decimal("0")
            giveback_pct = Decimal("0")

        if price_range > Decimal("0"):
            entry_quality_score = _quantize(
                _clamp_pct(((max_price - entry_price) / price_range) * _HUNDRED)
            )
            exit_quality_score = _quantize(
                _clamp_pct(((trade.fill_price - min_price) / price_range) * _HUNDRED)
            )
        else:
            entry_quality_score = Decimal("50")
            exit_quality_score = Decimal("50")

        details.append(
            TradeQualityDetail(
                order_id=trade.order_id,
                symbol=trade.symbol,
                entry_time=first_entry_time,
                exit_time=trade.event_time,
                quantity=matched_quantity,
                entry_price=entry_price,
                exit_price=trade.fill_price,
                realized_pnl=trade.realized_pnl,
                hold_seconds=hold_seconds,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
                captured_move_pct=captured_move_pct,
                giveback_pct=giveback_pct,
                entry_quality_score=entry_quality_score,
                exit_quality_score=exit_quality_score,
            )
        )

    details.sort(key=lambda detail: detail.exit_time, reverse=True)

    summary = TradeQualitySummary(
        total_closed_trades=len(details),
        average_mfe_pct=_average_decimal([detail.mfe_pct for detail in details]),
        average_mae_pct=_average_decimal([detail.mae_pct for detail in details]),
        average_captured_move_pct=_average_decimal([detail.captured_move_pct for detail in details]),
        average_giveback_pct=_average_decimal([detail.giveback_pct for detail in details]),
        average_entry_quality_score=_average_decimal([detail.entry_quality_score for detail in details]),
        average_exit_quality_score=_average_decimal([detail.exit_quality_score for detail in details]),
        longest_no_trade_seconds=_longest_no_trade_seconds(
            trades,
            start_date=start_date,
            end_date=end_date,
        ),
        hold_time_distribution=_hold_time_distribution(details),
    )
    return TradeQualityAnalytics(summary=summary, details=details)
