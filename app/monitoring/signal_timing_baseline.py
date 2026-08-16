"""Measured timing-quality baseline for current actionable advisory signals."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.storage.models import (
    HistoricalCandleRecord,
    SignalOutcomeSnapshotRecord,
    SignalTimingBaselineRecord,
    TradeRecord,
)
from app.storage.repositories import StorageRepository

TimingClassification = Literal[
    "early",
    "useful",
    "late",
    "chased",
    "false",
    "neutral",
    "insufficient_data",
]

TIMING_HORIZONS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}
TIMING_LOOKBACKS: dict[str, timedelta] = {
    "5m": timedelta(minutes=15),
    "15m": timedelta(minutes=45),
    "1h": timedelta(hours=3),
    "4h": timedelta(hours=12),
    "24h": timedelta(days=2),
}
ESTIMATED_ROUND_TRIP_COST_PCT = Decimal("0.1200")
MEANINGFUL_MOVE_PCT = Decimal("0.5000")
TARGET_PCT = Decimal("1.5000")
STOP_PCT = Decimal("1.0000")


@dataclass(slots=True, frozen=True)
class SignalTimingAggregate:
    """Aggregate timing metrics for a report bucket."""

    label: str
    sample_size: int
    average_move_consumed_pct: Decimal | None
    average_move_capture_ratio_pct: Decimal | None
    average_entry_efficiency_pct: Decimal | None
    average_lead_time_seconds: Decimal | None
    average_net_return_after_costs_pct: Decimal | None
    late_rate_pct: Decimal
    chase_rate_pct: Decimal
    useful_rate_pct: Decimal


@dataclass(slots=True, frozen=True)
class SignalTimingBaselineReport:
    """Current measured baseline for actionable signal timing quality."""

    generated_at: datetime
    actionable_snapshot_count: int
    evaluated_count: int
    pending_count: int
    insufficient_data_count: int
    classification_counts: dict[str, int]
    overall: SignalTimingAggregate
    by_horizon: list[SignalTimingAggregate] = field(default_factory=list)
    by_source: list[SignalTimingAggregate] = field(default_factory=list)
    recent_samples: list[SignalTimingBaselineRecord] = field(default_factory=list)
    definitions: dict[str, str] = field(default_factory=dict)


def evaluate_pending_signal_timing_baselines(
    *,
    repository: StorageRepository,
    as_of: datetime | None = None,
    retry_insufficient: bool = False,
) -> int:
    """Evaluate matured actionable snapshots and persist timing baselines idempotently."""

    evaluation_time = as_of or datetime.now(tz=UTC)
    snapshots = [
        snapshot
        for snapshot in repository.get_signal_outcome_snapshots()
        if _direction(snapshot.signal_type) is not None
    ]
    existing = {
        (item.signal_id, item.horizon): item
        for item in repository.get_signal_timing_baselines()
    }
    written = 0
    for snapshot in snapshots:
        for horizon, duration in TIMING_HORIZONS.items():
            current = existing.get((snapshot.id, horizon))
            if current is not None and (
                current.outcome_state == "evaluated"
                or (current.outcome_state == "insufficient_data" and not retry_insufficient)
            ):
                continue
            if evaluation_time < snapshot.timestamp + duration:
                continue
            baseline = evaluate_signal_timing_baseline(
                repository=repository,
                snapshot=snapshot,
                horizon=horizon,
                as_of=evaluation_time,
            )
            repository.upsert_signal_timing_baseline(baseline)
            written += 1
    return written


def evaluate_signal_timing_baseline(
    *,
    repository: StorageRepository,
    snapshot: SignalOutcomeSnapshotRecord,
    horizon: str,
    as_of: datetime | None = None,
) -> SignalTimingBaselineRecord:
    """Calculate one deterministic timing baseline without changing trading behavior."""

    if horizon not in TIMING_HORIZONS:
        raise ValueError(f"Unsupported timing baseline horizon: {horizon}")
    evaluation_time = as_of or datetime.now(tz=UTC)
    duration = TIMING_HORIZONS[horizon]
    expiry_seconds = int(duration.total_seconds())
    direction = _direction(snapshot.signal_type)
    if evaluation_time < snapshot.timestamp + duration:
        return _empty_baseline(
            snapshot=snapshot,
            horizon=horizon,
            direction=direction or "WAIT",
            expiry_seconds=expiry_seconds,
            state="pending",
            evaluated_at=evaluation_time,
        )
    if direction is None or snapshot.entry_price is None or snapshot.entry_price <= 0:
        return _empty_baseline(
            snapshot=snapshot,
            horizon=horizon,
            direction=direction or "WAIT",
            expiry_seconds=expiry_seconds,
            state="insufficient_data",
            evaluated_at=evaluation_time,
        )

    prior, future = _load_timing_candles(
        repository=repository,
        snapshot=snapshot,
        horizon=horizon,
    )
    if not prior or not future:
        return _empty_baseline(
            snapshot=snapshot,
            horizon=horizon,
            direction=direction,
            expiry_seconds=expiry_seconds,
            state="insufficient_data",
            evaluated_at=evaluation_time,
        )

    entry = snapshot.entry_price
    recent_swing_low = min(candle.low_price for candle in prior)
    recent_swing_high = max(candle.high_price for candle in prior)
    if direction == "BUY":
        setup_candle = min(prior, key=lambda candle: (candle.low_price, candle.open_time))
        setup_price = recent_swing_low
        favorable_price = max(candle.high_price for candle in future)
        adverse_price = min(candle.low_price for candle in future)
        move_before = _positive_pct(setup_price, entry)
        move_after = _directional_return(direction, entry, future[-1].close_price)
        mfe = _directional_return(direction, entry, favorable_price)
        mae = -_directional_return(direction, entry, adverse_price)
    else:
        setup_candle = max(prior, key=lambda candle: (candle.high_price, -candle.open_time.timestamp()))
        setup_price = recent_swing_high
        favorable_price = min(candle.low_price for candle in future)
        adverse_price = max(candle.high_price for candle in future)
        move_before = _positive_pct(entry, setup_price)
        move_after = _directional_return(direction, entry, future[-1].close_price)
        mfe = _directional_return(direction, entry, favorable_price)
        mae = -_directional_return(direction, entry, adverse_price)

    full_move = max(Decimal("0"), move_before) + max(Decimal("0"), mfe)
    consumed = _ratio(move_before, full_move)
    capture = _ratio(mfe, full_move)
    terminal_gross = _directional_return(direction, entry, future[-1].close_price)
    net_return = terminal_gross - ESTIMATED_ROUND_TRIP_COST_PCT
    entry_efficiency = _signed_ratio(terminal_gross, mfe) if mfe > 0 else Decimal("0")
    lead_time = _lead_time_seconds(
        direction=direction,
        signal_time=snapshot.timestamp,
        setup_price=setup_price,
        prior=[item for item in prior if item.open_time >= setup_candle.open_time],
        future=future,
    )
    target_time, stop_time = _target_stop_times(
        direction=direction,
        entry=entry,
        signal_time=snapshot.timestamp,
        candles=future,
    )
    entry_latency = _signal_to_entry_latency(
        repository=repository,
        snapshot=snapshot,
        direction=direction,
        duration=duration,
    )
    volatility = _positive_pct(recent_swing_low, recent_swing_high)
    regime = _infer_regime(prior)
    classification, reasons = _classify(
        consumed=consumed,
        capture=capture,
        mfe=mfe,
        mae=mae,
        net_return=net_return,
        lead_time_seconds=lead_time,
    )
    return SignalTimingBaselineRecord(
        id=None,
        signal_id=snapshot.id,
        horizon=horizon,
        symbol=snapshot.symbol,
        source=snapshot.source,
        direction=direction,
        signal_time=snapshot.timestamp,
        setup_start_time=setup_candle.open_time,
        setup_start_price=_q(setup_price),
        activation_price=_q(entry),
        recent_swing_low=_q(recent_swing_low),
        recent_swing_high=_q(recent_swing_high),
        horizon_end_price=_q(future[-1].close_price),
        max_favorable_price=_q(favorable_price),
        max_adverse_price=_q(adverse_price),
        move_before_signal_pct=_q(move_before),
        move_after_signal_pct=_q(move_after),
        max_favorable_excursion_pct=_q(mfe),
        max_adverse_excursion_pct=_q(mae),
        full_move_pct=_q(full_move),
        move_already_consumed_pct=_q(consumed),
        move_capture_ratio_pct=_q(capture),
        entry_efficiency_pct=_q(entry_efficiency),
        pre_move_lead_time_seconds=lead_time,
        signal_to_entry_latency_seconds=entry_latency,
        time_to_target_seconds=target_time,
        time_to_stop_seconds=stop_time,
        expiry_seconds=expiry_seconds,
        net_return_after_costs_pct=_q(net_return),
        estimated_round_trip_cost_pct=ESTIMATED_ROUND_TRIP_COST_PCT,
        realized_volatility_pct=_q(volatility),
        regime_label=regime,
        liquidity_context=snapshot.liquidity_bias or snapshot.sweep_risk,
        classification=classification,
        classification_reasons=reasons,
        outcome_state="evaluated",
        evaluated_at=evaluation_time,
    )


def build_signal_timing_baseline_report(
    *,
    repository: StorageRepository,
    symbol: str | None = None,
    source: str | None = None,
    horizon: str | None = None,
    recent_limit: int = 50,
) -> SignalTimingBaselineReport:
    """Build an operator-facing timing baseline report from persisted measurements."""

    rows = repository.get_signal_timing_baselines(
        symbol=symbol,
        source=source,
        horizon=horizon,
    )
    actionable = [
        item
        for item in repository.get_signal_outcome_snapshots(symbol=symbol, source=source)
        if _direction(item.signal_type) is not None
    ]
    evaluated = [item for item in rows if item.outcome_state == "evaluated"]
    counts = Counter(item.classification for item in rows)
    horizons = sorted({item.horizon for item in evaluated}, key=_horizon_sort_key)
    sources = sorted({item.source for item in evaluated})
    return SignalTimingBaselineReport(
        generated_at=datetime.now(tz=UTC),
        actionable_snapshot_count=len(actionable),
        evaluated_count=len(evaluated),
        pending_count=max(
            0,
            len(actionable) * (1 if horizon is not None else len(TIMING_HORIZONS)) - len(rows),
        ),
        insufficient_data_count=sum(item.outcome_state == "insufficient_data" for item in rows),
        classification_counts=dict(sorted(counts.items())),
        overall=_aggregate("overall", evaluated),
        by_horizon=[_aggregate(item, [row for row in evaluated if row.horizon == item]) for item in horizons],
        by_source=[_aggregate(item, [row for row in evaluated if row.source == item]) for item in sources],
        recent_samples=rows[:recent_limit],
        definitions={
            "setup_start_price": (
                "Derived lookback swing proxy for the move origin; the current bot does not yet emit a forming-setup event."
            ),
            "move_already_consumed_pct": "Share of the measured complete directional move that occurred before activation.",
            "move_capture_ratio_pct": "Share of the complete measured move still available after activation.",
            "entry_efficiency_pct": "Terminal directional return as a share of maximum favorable excursion after activation.",
            "pre_move_lead_time_seconds": "Positive when the meaningful move followed the signal; negative when it had already happened.",
            "signal_to_entry_latency_seconds": (
                "Time to the nearest matching executed paper order for the symbol and side, when one exists."
            ),
            "net_return_after_costs_pct": "Horizon-end directional return after the configured 0.12% round-trip cost estimate.",
            "classification_thresholds": (
                "Chased: >=70% consumed; late: >=50% consumed or non-positive lead; "
                "early: positive lead and <35% consumed; false: no 0.5% favorable move."
            ),
        },
    )


def _load_timing_candles(
    *,
    repository: StorageRepository,
    snapshot: SignalOutcomeSnapshotRecord,
    horizon: str,
) -> tuple[list[HistoricalCandleRecord], list[HistoricalCandleRecord]]:
    start = snapshot.timestamp - TIMING_LOOKBACKS[horizon]
    end = snapshot.timestamp + TIMING_HORIZONS[horizon]
    loader = (
        repository.get_futures_historical_candles
        if snapshot.source in {"scanner", "futures_scanner"}
        else repository.get_historical_candles
    )
    for interval in ("1m", "5m", "15m", "1h"):
        candles = loader(symbol=snapshot.symbol, interval=interval, start_time=start, end_time=end)
        prior = [item for item in candles if item.close_time <= snapshot.timestamp]
        future = [item for item in candles if item.close_time > snapshot.timestamp and item.open_time < end]
        if prior and future:
            return prior, future
    return [], []


def _direction(value: str) -> Literal["BUY", "SELL"] | None:
    normalized = value.strip().upper()
    if normalized in {"BUY", "LONG"}:
        return "BUY"
    if normalized in {"SELL", "SHORT"}:
        return "SELL"
    return None


def _positive_pct(low: Decimal, high: Decimal) -> Decimal:
    if low <= 0:
        return Decimal("0")
    return ((high - low) / low) * Decimal("100")


def _directional_return(direction: str, entry: Decimal, price: Decimal) -> Decimal:
    raw = _positive_pct(entry, price)
    return raw if direction == "BUY" else -raw


def _ratio(part: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return max(Decimal("0"), min(Decimal("100"), (part / total) * Decimal("100")))


def _signed_ratio(part: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return max(Decimal("-100"), min(Decimal("100"), (part / total) * Decimal("100")))


def _lead_time_seconds(
    *,
    direction: str,
    signal_time: datetime,
    setup_price: Decimal,
    prior: Sequence[HistoricalCandleRecord],
    future: Sequence[HistoricalCandleRecord],
) -> int | None:
    if direction == "BUY":
        threshold = setup_price * (Decimal("1") + MEANINGFUL_MOVE_PCT / Decimal("100"))
        prior_hit = next((item for item in prior if item.high_price >= threshold), None)
        future_hit = next((item for item in future if item.high_price >= threshold), None)
    else:
        threshold = setup_price * (Decimal("1") - MEANINGFUL_MOVE_PCT / Decimal("100"))
        prior_hit = next((item for item in prior if item.low_price <= threshold), None)
        future_hit = next((item for item in future if item.low_price <= threshold), None)
    if prior_hit is not None:
        return int((prior_hit.close_time - signal_time).total_seconds())
    if future_hit is not None:
        return int((future_hit.close_time - signal_time).total_seconds())
    return None


def _target_stop_times(
    *,
    direction: str,
    entry: Decimal,
    signal_time: datetime,
    candles: Sequence[HistoricalCandleRecord],
) -> tuple[int | None, int | None]:
    if direction == "BUY":
        target = entry * (Decimal("1") + TARGET_PCT / Decimal("100"))
        stop = entry * (Decimal("1") - STOP_PCT / Decimal("100"))
        target_candle = next((item for item in candles if item.high_price >= target), None)
        stop_candle = next((item for item in candles if item.low_price <= stop), None)
    else:
        target = entry * (Decimal("1") - TARGET_PCT / Decimal("100"))
        stop = entry * (Decimal("1") + STOP_PCT / Decimal("100"))
        target_candle = next((item for item in candles if item.low_price <= target), None)
        stop_candle = next((item for item in candles if item.high_price >= stop), None)
    return (
        int((target_candle.close_time - signal_time).total_seconds()) if target_candle else None,
        int((stop_candle.close_time - signal_time).total_seconds()) if stop_candle else None,
    )


def _signal_to_entry_latency(
    *,
    repository: StorageRepository,
    snapshot: SignalOutcomeSnapshotRecord,
    direction: str,
    duration: timedelta,
) -> int | None:
    if snapshot.source in {"scanner", "futures_scanner"}:
        expected_side = "LONG" if direction == "BUY" else "SHORT"
        futures_fills = [
            fill
            for fill in repository.get_futures_paper_fills(symbol=snapshot.symbol)
            if fill.status == "executed"
            and fill.side.upper() == expected_side
            and snapshot.timestamp <= fill.event_time <= snapshot.timestamp + duration
        ]
        if futures_fills:
            first_fill = min(futures_fills, key=lambda item: item.event_time)
            return int((first_fill.event_time - snapshot.timestamp).total_seconds())
    trades: Sequence[TradeRecord] = repository.get_trade_history(
        symbol=snapshot.symbol,
        start_date=snapshot.timestamp.date(),
        end_date=(snapshot.timestamp + duration).date(),
    )
    matching = [
        trade
        for trade in trades
        if trade.status == "executed"
        and trade.side.upper() == direction
        and snapshot.timestamp <= trade.event_time <= snapshot.timestamp + duration
    ]
    if not matching:
        return None
    return int((min(matching, key=lambda item: item.event_time).event_time - snapshot.timestamp).total_seconds())


def _infer_regime(candles: Sequence[HistoricalCandleRecord]) -> str:
    first = candles[0].close_price
    last = candles[-1].close_price
    change = _positive_pct(first, last)
    if change >= Decimal("0.5000"):
        return "trending_up"
    if change <= Decimal("-0.5000"):
        return "trending_down"
    return "ranging"


def _classify(
    *,
    consumed: Decimal,
    capture: Decimal,
    mfe: Decimal,
    mae: Decimal,
    net_return: Decimal,
    lead_time_seconds: int | None,
) -> tuple[TimingClassification, tuple[str, ...]]:
    if consumed >= Decimal("70"):
        return "chased", ("At least 70% of the measured move occurred before activation.",)
    if consumed >= Decimal("50") or (lead_time_seconds is not None and lead_time_seconds <= 0):
        return "late", ("The meaningful move was already underway when the signal activated.",)
    if mfe < MEANINGFUL_MOVE_PCT and (net_return <= 0 or mae >= mfe):
        return "false", ("No meaningful favorable move followed activation.",)
    if lead_time_seconds is not None and lead_time_seconds > 0 and consumed < Decimal("35"):
        return "early", ("Activation preceded the meaningful move with limited prior move consumption.",)
    if net_return > 0 and capture >= Decimal("50"):
        return "useful", ("The signal retained positive post-cost return and at least half of the measured move.",)
    return "neutral", ("The sample was neither clearly timely nor clearly late under baseline thresholds.",)


def _empty_baseline(
    *,
    snapshot: SignalOutcomeSnapshotRecord,
    horizon: str,
    direction: str,
    expiry_seconds: int,
    state: str,
    evaluated_at: datetime,
) -> SignalTimingBaselineRecord:
    return SignalTimingBaselineRecord(
        id=None,
        signal_id=snapshot.id,
        horizon=horizon,
        symbol=snapshot.symbol,
        source=snapshot.source,
        direction=direction,
        signal_time=snapshot.timestamp,
        setup_start_time=None,
        setup_start_price=None,
        activation_price=snapshot.entry_price,
        recent_swing_low=None,
        recent_swing_high=None,
        horizon_end_price=None,
        max_favorable_price=None,
        max_adverse_price=None,
        move_before_signal_pct=None,
        move_after_signal_pct=None,
        max_favorable_excursion_pct=None,
        max_adverse_excursion_pct=None,
        full_move_pct=None,
        move_already_consumed_pct=None,
        move_capture_ratio_pct=None,
        entry_efficiency_pct=None,
        pre_move_lead_time_seconds=None,
        signal_to_entry_latency_seconds=None,
        time_to_target_seconds=None,
        time_to_stop_seconds=None,
        expiry_seconds=expiry_seconds,
        net_return_after_costs_pct=None,
        estimated_round_trip_cost_pct=ESTIMATED_ROUND_TRIP_COST_PCT,
        realized_volatility_pct=None,
        regime_label=None,
        liquidity_context=snapshot.liquidity_bias or snapshot.sweep_risk,
        classification="insufficient_data",
        classification_reasons=("Sufficient pre-signal and post-signal candle history was unavailable.",),
        outcome_state=state,
        evaluated_at=evaluated_at,
    )


def _aggregate(label: str, rows: Sequence[SignalTimingBaselineRecord]) -> SignalTimingAggregate:
    count = len(rows)
    classifications = Counter(item.classification for item in rows)
    return SignalTimingAggregate(
        label=label,
        sample_size=count,
        average_move_consumed_pct=_average(item.move_already_consumed_pct for item in rows),
        average_move_capture_ratio_pct=_average(item.move_capture_ratio_pct for item in rows),
        average_entry_efficiency_pct=_average(item.entry_efficiency_pct for item in rows),
        average_lead_time_seconds=_average_decimal(item.pre_move_lead_time_seconds for item in rows),
        average_net_return_after_costs_pct=_average(item.net_return_after_costs_pct for item in rows),
        late_rate_pct=_rate(classifications["late"] + classifications["chased"], count),
        chase_rate_pct=_rate(classifications["chased"], count),
        useful_rate_pct=_rate(classifications["early"] + classifications["useful"], count),
    )


def _average(values: Iterable[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    return _q(sum(present, Decimal("0")) / len(present)) if present else None


def _average_decimal(values: Iterable[int | None]) -> Decimal | None:
    present = [Decimal(value) for value in values if value is not None]
    return _q(sum(present, Decimal("0")) / len(present)) if present else None


def _rate(part: int, total: int) -> Decimal:
    return _q(Decimal(part) * Decimal("100") / Decimal(total)) if total else Decimal("0.0000")


def _horizon_sort_key(value: str) -> int:
    return list(TIMING_HORIZONS).index(value) if value in TIMING_HORIZONS else 999


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
