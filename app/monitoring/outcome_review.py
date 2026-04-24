"""Paper trade outcome review analytics for tuning paper profiles."""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.storage.models import FillRecord, RunnerEventRecord, TradeRecord


@dataclass(slots=True)
class SymbolTradeSummary:
    """Executed trade count for one symbol."""

    symbol: str
    trade_count: int


@dataclass(slots=True)
class SessionAnalytics:
    """Operator-facing paper-trade session analytics."""

    trades_per_hour: Decimal | None
    trades_per_symbol: list[SymbolTradeSummary]
    win_rate: Decimal | None
    average_pnl: Decimal | None
    average_hold_seconds: int | None
    fees_paid: Decimal
    idle_duration_seconds: int | None
    total_closed_trades: int


@dataclass(slots=True)
class BlockerFrequency:
    """Frequency of one trade blocker category."""

    blocker_key: str
    label: str
    count: int
    frequency_pct: Decimal


@dataclass(slots=True)
class ProfileComparison:
    """Trade results grouped by paper trading profile."""

    profile: str
    trade_count: int
    realized_pnl: Decimal
    win_rate: Decimal | None
    average_expectancy: Decimal | None


@dataclass(slots=True)
class ExecutionSourceComparison:
    """Trade results grouped by manual vs auto execution source."""

    execution_source: str
    trade_count: int
    realized_pnl: Decimal
    win_rate: Decimal | None
    average_expectancy: Decimal | None


@dataclass(slots=True)
class TuningSuggestion:
    """Deterministic tuning suggestion derived from paper outcomes."""

    summary: str


@dataclass(slots=True)
class PaperTradeReview:
    """Combined operator review analytics for paper trading."""

    symbol: str | None
    start_date: date | None
    end_date: date | None
    session: SessionAnalytics
    blockers: list[BlockerFrequency]
    profiles: list[ProfileComparison]
    execution_sources: list[ExecutionSourceComparison]
    suggestions: list[TuningSuggestion]


@dataclass(slots=True)
class _OpenLot:
    """One open buy lot used for hold-time matching."""

    entry_time: datetime
    quantity_remaining: Decimal


_BLOCKER_LABELS: dict[str, str] = {
    "low_volatility": "Low volatility",
    "weak_signal": "Weak signal",
    "spread_too_wide": "Spread too wide",
    "edge_below_fees": "Edge below fees",
    "insufficient_candles": "Insufficient candles",
    "no_trend_confirmation": "No trend confirmation",
}

_REASON_CODE_BLOCKERS: dict[str, str] = {
    "VOL_TOO_LOW": "low_volatility",
    "MICROSTRUCTURE_UNHEALTHY": "spread_too_wide",
    "EDGE_BELOW_COSTS": "edge_below_fees",
    "EXPECTED_EDGE_TOO_SMALL": "edge_below_fees",
    "WAITING_FOR_HISTORY": "insufficient_candles",
    "MISSING_EMA": "insufficient_candles",
    "MISSING_ATR_CONTEXT": "insufficient_candles",
    "REGIME_NOT_TREND": "no_trend_confirmation",
    "EMA_NOT_BULLISH": "weak_signal",
    "NON_ACTIONABLE_SIGNAL": "weak_signal",
}


def _parse_payload(record: RunnerEventRecord) -> dict[str, object]:
    """Parse a runner event payload into a plain dictionary."""

    try:
        parsed = json.loads(record.payload_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _closed_trades(trades: list[TradeRecord]) -> list[TradeRecord]:
    """Return executed closing trades used for outcome analytics."""

    return [trade for trade in trades if trade.status == "executed" and trade.side == "SELL"]


def _to_optional_average(total: Decimal, count: int) -> Decimal | None:
    """Return an average only when the divisor is positive."""

    if count <= 0:
        return None
    return (total / Decimal(count)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _to_optional_rate(numerator: int, denominator: int) -> Decimal | None:
    """Return a percentage rate rounded for operator display."""

    if denominator <= 0:
        return None
    return (
        (Decimal(numerator) / Decimal(denominator)) * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _average_hold_seconds(trades: list[TradeRecord]) -> int | None:
    """Return weighted average hold time for closed trades."""

    open_lots: deque[_OpenLot] = deque()
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
        while quantity_remaining > Decimal("0") and open_lots:
            lot = open_lots[0]
            matched_quantity = min(lot.quantity_remaining, quantity_remaining)
            hold_seconds_total += Decimal((trade.event_time - lot.entry_time).total_seconds()) * matched_quantity
            matched_quantity_total += matched_quantity
            lot.quantity_remaining -= matched_quantity
            quantity_remaining -= matched_quantity
            if lot.quantity_remaining <= Decimal("0"):
                open_lots.popleft()

    if matched_quantity_total <= Decimal("0"):
        return None
    return int((hold_seconds_total / matched_quantity_total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _trades_per_hour(trades: list[TradeRecord], events: list[RunnerEventRecord]) -> Decimal | None:
    """Return executed trade cadence per hour over the active event window."""

    executed_trades = [trade for trade in trades if trade.status == "executed"]
    if not executed_trades:
        return None
    timestamps = [trade.event_time for trade in executed_trades]
    timestamps.extend(event.event_time for event in events)
    if len(timestamps) < 2:
        return Decimal(len(executed_trades)).quantize(Decimal("0.01"))
    active_seconds = max((max(timestamps) - min(timestamps)).total_seconds(), 1)
    return (
        Decimal(len(executed_trades)) * Decimal("3600") / Decimal(active_seconds)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _trades_per_symbol(trades: list[TradeRecord]) -> list[SymbolTradeSummary]:
    """Return executed trade counts grouped by symbol."""

    counts = Counter(trade.symbol for trade in trades if trade.status == "executed")
    return [
        SymbolTradeSummary(symbol=symbol, trade_count=count)
        for symbol, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _idle_duration_seconds(trades: list[TradeRecord], events: list[RunnerEventRecord]) -> int | None:
    """Return time since the latest executed trade within the active event window."""

    executed_trade_times = [trade.event_time for trade in trades if trade.status == "executed"]
    event_times = [event.event_time for event in events]
    if not executed_trade_times or not event_times:
        return None
    latest_trade_time = max(executed_trade_times)
    latest_event_time = max(event_times)
    return max(int((latest_event_time - latest_trade_time).total_seconds()), 0)


def _build_session_analytics(trades: list[TradeRecord], fills: list[FillRecord], events: list[RunnerEventRecord]) -> SessionAnalytics:
    """Build session-level review analytics."""

    closed_trades = _closed_trades(trades)
    realized_total = sum((trade.realized_pnl for trade in closed_trades), start=Decimal("0"))
    win_count = sum(1 for trade in closed_trades if trade.realized_pnl > Decimal("0"))
    fees_paid = sum((fill.fee_paid for fill in fills), start=Decimal("0"))
    return SessionAnalytics(
        trades_per_hour=_trades_per_hour(trades, events),
        trades_per_symbol=_trades_per_symbol(trades),
        win_rate=_to_optional_rate(win_count, len(closed_trades)),
        average_pnl=_to_optional_average(realized_total, len(closed_trades)),
        average_hold_seconds=_average_hold_seconds(trades),
        fees_paid=fees_paid,
        idle_duration_seconds=_idle_duration_seconds(trades, events),
        total_closed_trades=len(closed_trades),
    )


def _extract_reason_codes(events: list[RunnerEventRecord]) -> list[str]:
    """Return all blocker-related reason codes from persisted runner events."""

    reason_codes: list[str] = []
    for event in events:
        payload = _parse_payload(event)
        raw_codes = payload.get("reason_codes", [])
        if isinstance(raw_codes, (list, tuple)):
            reason_codes.extend(str(item) for item in raw_codes)
        elif isinstance(raw_codes, str):
            reason_codes.append(raw_codes)
    return reason_codes


def _build_blockers(events: list[RunnerEventRecord]) -> list[BlockerFrequency]:
    """Build blocker frequency percentages from persisted runner events."""

    reason_codes = _extract_reason_codes(
        [
            event
            for event in events
            if event.event_type in {"trade_blocked", "manual_trade_request", "risk_decision", "signal_generated"}
        ]
    )
    blocker_counts = Counter(
        _REASON_CODE_BLOCKERS[reason_code]
        for reason_code in reason_codes
        if reason_code in _REASON_CODE_BLOCKERS
    )
    total = sum(blocker_counts.values())
    if total <= 0:
        return []

    return [
        BlockerFrequency(
            blocker_key=blocker_key,
            label=_BLOCKER_LABELS[blocker_key],
            count=count,
            frequency_pct=((Decimal(count) / Decimal(total)) * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
        )
        for blocker_key, count in sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _build_profile_comparisons(trades: list[TradeRecord]) -> list[ProfileComparison]:
    """Build paper trade profile comparisons from persisted trade metadata."""

    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in _closed_trades(trades):
        grouped[trade.trading_profile].append(trade)

    comparisons: list[ProfileComparison] = []
    for profile in ("conservative", "balanced", "aggressive"):
        profile_trades = grouped.get(profile, [])
        realized_pnl = sum((trade.realized_pnl for trade in profile_trades), start=Decimal("0"))
        win_count = sum(1 for trade in profile_trades if trade.realized_pnl > Decimal("0"))
        comparisons.append(
            ProfileComparison(
                profile=profile,
                trade_count=len(profile_trades),
                realized_pnl=realized_pnl,
                win_rate=_to_optional_rate(win_count, len(profile_trades)),
                average_expectancy=_to_optional_average(realized_pnl, len(profile_trades)),
            )
        )
    return comparisons


def _build_execution_source_comparisons(trades: list[TradeRecord]) -> list[ExecutionSourceComparison]:
    """Build manual-vs-auto paper trade comparisons."""

    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in _closed_trades(trades):
        grouped[trade.execution_source].append(trade)

    comparisons: list[ExecutionSourceComparison] = []
    for execution_source in ("auto", "manual"):
        source_trades = grouped.get(execution_source, [])
        realized_pnl = sum((trade.realized_pnl for trade in source_trades), start=Decimal("0"))
        win_count = sum(1 for trade in source_trades if trade.realized_pnl > Decimal("0"))
        comparisons.append(
            ExecutionSourceComparison(
                execution_source=execution_source,
                trade_count=len(source_trades),
                realized_pnl=realized_pnl,
                win_rate=_to_optional_rate(win_count, len(source_trades)),
                average_expectancy=_to_optional_average(realized_pnl, len(source_trades)),
            )
        )
    return comparisons


def _build_tuning_suggestions(
    *,
    symbol: str | None,
    session: SessionAnalytics,
    blockers: list[BlockerFrequency],
    profiles: list[ProfileComparison],
) -> list[TuningSuggestion]:
    """Build deterministic tuning suggestions for the selected scope."""

    scope_label = symbol or "this paper session"
    suggestions: list[TuningSuggestion] = []

    top_blocker = blockers[0] if blockers else None
    if top_blocker is not None and top_blocker.blocker_key == "edge_below_fees":
        suggestions.append(
            TuningSuggestion(
                summary=f"{scope_label} is frequently blocked because expected edge stays below paper costs.",
            )
        )
    if top_blocker is not None and top_blocker.blocker_key == "low_volatility":
        suggestions.append(
            TuningSuggestion(
                summary=f"{scope_label} is spending most of its time in quiet conditions, so balanced mode may stay underactive.",
            )
        )
    if top_blocker is not None and top_blocker.blocker_key == "spread_too_wide":
        suggestions.append(
            TuningSuggestion(
                summary=f"{scope_label} is often blocked by wide spread or weak microstructure. Execution quality is likely thin.",
            )
        )

    balanced = next((item for item in profiles if item.profile == "balanced"), None)
    if (
        balanced is not None
        and balanced.trade_count >= 3
        and balanced.average_expectancy is not None
        and balanced.average_expectancy < Decimal("0")
        and session.trades_per_hour is not None
        and session.trades_per_hour >= Decimal("1.00")
    ):
        suggestions.append(
            TuningSuggestion(
                summary=f"Balanced mode on {scope_label} appears to overtrade relative to realized edge.",
            )
        )

    aggressive = next((item for item in profiles if item.profile == "aggressive"), None)
    if (
        aggressive is not None
        and aggressive.trade_count > 0
        and aggressive.average_expectancy is not None
        and aggressive.average_expectancy < Decimal("0")
    ):
        suggestions.append(
            TuningSuggestion(
                summary=f"Aggressive mode on {scope_label} is producing negative expectancy. Use it only for deliberate testing.",
            )
        )

    if not suggestions:
        suggestions.append(
            TuningSuggestion(
                summary=f"{scope_label} has limited blocker pressure so far. Keep collecting paper trades before retuning thresholds.",
            )
        )
    return suggestions[:3]


def build_paper_trade_review(
    *,
    trades: list[TradeRecord],
    fills: list[FillRecord],
    events: list[RunnerEventRecord],
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PaperTradeReview:
    """Build paper trade outcome review analytics for one symbol/date scope."""

    session = _build_session_analytics(trades, fills, events)
    blockers = _build_blockers(events)
    profiles = _build_profile_comparisons(trades)
    execution_sources = _build_execution_source_comparisons(trades)
    suggestions = _build_tuning_suggestions(
        symbol=symbol,
        session=session,
        blockers=blockers,
        profiles=profiles,
    )
    return PaperTradeReview(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        session=session,
        blockers=blockers,
        profiles=profiles,
        execution_sources=execution_sources,
        suggestions=suggestions,
    )
