"""Paper-only validation reporting for futures scanner signal outcomes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random
from uuid import uuid4

from app.monitoring.futures_opportunity_scanner import FuturesOpportunityScanReport, FuturesPaperSignal
from app.storage.models import (
    HistoricalCandleRecord,
    ScannerValidationOutcomeRecord,
    ScannerValidationSnapshotRecord,
)
from app.storage.repositories import StorageRepository


SCANNER_VALIDATION_HORIZONS = ("15m", "1h", "4h", "24h")
ESTIMATED_FEE_PCT = Decimal("0.0800")
ESTIMATED_SLIPPAGE_PCT = Decimal("0.0400")
MIN_REPORT_SAMPLE_SIZE = 10


@dataclass(slots=True)
class ScannerValidationGroupPerformance:
    """Aggregate performance for one report grouping."""

    name: str
    sample_size: int
    win_rate: Decimal | None
    average_net_return: Decimal | None
    expectancy: Decimal | None


@dataclass(slots=True)
class ScannerBaselineComparison:
    """Scanner picks compared with random baseline snapshots."""

    scanner_sample_size: int
    random_baseline_sample_size: int
    scanner_average_net_return: Decimal | None
    random_baseline_average_net_return: Decimal | None
    scanner_win_rate: Decimal | None
    random_baseline_win_rate: Decimal | None
    edge_vs_random: Decimal | None


@dataclass(slots=True)
class StopLossTakeProfitAnalysis:
    """TP/SL hit-rate summary for evaluated directional scanner snapshots."""

    sample_size: int
    take_profit_hit_rate: Decimal | None
    stop_loss_hit_rate: Decimal | None
    neither_hit_rate: Decimal | None
    take_profit_first: int
    stop_loss_first: int


@dataclass(slots=True)
class ScannerValidationReport:
    """Full scanner validation report payload."""

    generated_at: datetime
    total_snapshots: int
    evaluated_snapshots: int
    pending_snapshots: int
    win_rate: Decimal | None
    expectancy: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    average_net_return: Decimal | None
    max_drawdown: Decimal | None
    scanner_vs_random_baseline: ScannerBaselineComparison
    opportunity_score_bucket_performance: list[ScannerValidationGroupPerformance]
    direction_performance: list[ScannerValidationGroupPerformance]
    horizon_performance: list[ScannerValidationGroupPerformance]
    stop_loss_take_profit_analysis: StopLossTakeProfitAnalysis
    best_symbols: list[ScannerValidationGroupPerformance]
    worst_symbols: list[ScannerValidationGroupPerformance]
    best_regimes: list[ScannerValidationGroupPerformance]
    weak_conditions: list[str]
    conclusion: str
    warnings: list[str] = field(default_factory=list)


def persist_scanner_validation_snapshots(
    *,
    repository: StorageRepository,
    report: FuturesOpportunityScanReport,
    random_baseline_size: int = 3,
    scan_id: str | None = None,
) -> tuple[str, int]:
    """Persist one scanner run as validation snapshots plus a random baseline."""

    resolved_scan_id = scan_id or f"scan_{uuid4().hex[:16]}"
    snapshots: list[ScannerValidationSnapshotRecord] = []
    snapshots.extend(
        _snapshot_records_for_group(
            scan_id=resolved_scan_id,
            signals=report.long_candidates,
            candidate_group="top_long",
        )
    )
    snapshots.extend(
        _snapshot_records_for_group(
            scan_id=resolved_scan_id,
            signals=report.short_candidates,
            candidate_group="top_short",
        )
    )
    snapshots.extend(
        _snapshot_records_for_group(
            scan_id=resolved_scan_id,
            signals=report.neutral_candidates,
            candidate_group="neutral",
        )
    )

    baseline_pool = list(report.long_candidates + report.short_candidates + report.neutral_candidates)
    baseline_candidates = _random_baseline_candidates(
        baseline_pool,
        scan_id=resolved_scan_id,
        sample_size=random_baseline_size,
    )
    snapshots.extend(
        _snapshot_records_for_group(
            scan_id=resolved_scan_id,
            signals=baseline_candidates,
            candidate_group="random_baseline",
        )
    )
    inserted = repository.insert_scanner_validation_snapshots(snapshots)
    return resolved_scan_id, inserted


def evaluate_pending_scanner_snapshots(
    *,
    repository: StorageRepository,
    as_of: datetime | None = None,
) -> int:
    """Evaluate pending scanner snapshots for fixed horizons using stored candles."""

    evaluation_time = as_of or datetime.now(tz=UTC)
    snapshots = repository.get_scanner_validation_snapshots()
    existing = repository.get_scanner_validation_outcomes(
        snapshot_ids=[snapshot.id for snapshot in snapshots if snapshot.id is not None]
    )
    existing_by_key = {(outcome.snapshot_id, outcome.horizon): outcome for outcome in existing}
    written = 0
    for snapshot in snapshots:
        if snapshot.id is None:
            continue
        for horizon in SCANNER_VALIDATION_HORIZONS:
            previous = existing_by_key.get((snapshot.id, horizon))
            if previous is not None and previous.outcome_state in {"win", "loss", "neutral"}:
                continue
            outcome = evaluate_scanner_snapshot_outcome(
                repository=repository,
                snapshot=snapshot,
                horizon=horizon,
                as_of=evaluation_time,
            )
            repository.upsert_scanner_validation_outcome(outcome)
            written += 1
    return written


def evaluate_scanner_snapshot_outcome(
    *,
    repository: StorageRepository,
    snapshot: ScannerValidationSnapshotRecord,
    horizon: str,
    as_of: datetime | None = None,
) -> ScannerValidationOutcomeRecord:
    """Calculate one fixed-horizon scanner outcome from stored candles."""

    evaluation_time = as_of or datetime.now(tz=UTC)
    target_time = snapshot.timestamp + _horizon_delta(horizon)
    if evaluation_time < target_time:
        return _pending_outcome(snapshot=snapshot, horizon=horizon, evaluated_at=evaluation_time)

    candles = _load_outcome_candles(repository, symbol=snapshot.symbol, start=snapshot.timestamp, end=target_time)
    future = next((candle for candle in candles if candle.close_time >= target_time), None)
    if snapshot.price_at_scan is None or snapshot.price_at_scan <= Decimal("0") or future is None:
        return _insufficient_outcome(snapshot=snapshot, horizon=horizon, evaluated_at=evaluation_time)

    price_at_scan = snapshot.price_at_scan
    future_price = future.close_price
    gross_return = _gross_return_pct(
        direction=snapshot.direction,
        entry_price=price_at_scan,
        future_price=future_price,
    )
    if gross_return is None:
        return ScannerValidationOutcomeRecord(
            id=None,
            snapshot_id=snapshot.id or 0,
            horizon=horizon,
            future_price=future_price,
            gross_return_pct=None,
            estimated_fee_pct=ESTIMATED_FEE_PCT,
            estimated_slippage_pct=ESTIMATED_SLIPPAGE_PCT,
            net_return_pct=None,
            direction_correct=None,
            max_favorable_move_pct=None,
            max_adverse_move_pct=None,
            take_profit_hit=False,
            stop_loss_hit=False,
            first_exit=None,
            outcome_state="neutral",
            evaluated_at=evaluation_time,
        )

    net_return = _quantize_pct(gross_return - ESTIMATED_FEE_PCT - ESTIMATED_SLIPPAGE_PCT)
    mfe, mae = _favorable_adverse_moves(
        direction=snapshot.direction,
        entry_price=price_at_scan,
        candles=candles,
    )
    take_profit_hit, stop_loss_hit, first_exit = _tp_sl_state(snapshot=snapshot, candles=candles)
    state = "win" if net_return > Decimal("0") else ("loss" if net_return < Decimal("0") else "neutral")
    return ScannerValidationOutcomeRecord(
        id=None,
        snapshot_id=snapshot.id or 0,
        horizon=horizon,
        future_price=future_price,
        gross_return_pct=_quantize_pct(gross_return),
        estimated_fee_pct=ESTIMATED_FEE_PCT,
        estimated_slippage_pct=ESTIMATED_SLIPPAGE_PCT,
        net_return_pct=net_return,
        direction_correct=net_return > Decimal("0"),
        max_favorable_move_pct=mfe,
        max_adverse_move_pct=mae,
        take_profit_hit=take_profit_hit,
        stop_loss_hit=stop_loss_hit,
        first_exit=first_exit,
        outcome_state=state,
        evaluated_at=evaluation_time,
    )


def build_scanner_validation_report(
    *,
    snapshots: Sequence[ScannerValidationSnapshotRecord],
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    start_date: date | None = None,
    end_date: date | None = None,
    horizon: str | None = None,
    direction: str | None = None,
    min_opportunity_score: int | None = None,
    symbol: str | None = None,
) -> ScannerValidationReport:
    """Build the scanner validation report from stored snapshots and outcomes."""

    filtered_snapshots = _filter_snapshots(
        snapshots=snapshots,
        start_date=start_date,
        end_date=end_date,
        direction=direction,
        min_opportunity_score=min_opportunity_score,
        symbol=symbol,
    )
    ids = {snapshot.id for snapshot in filtered_snapshots if snapshot.id is not None}
    snapshots_by_id = {snapshot.id: snapshot for snapshot in filtered_snapshots if snapshot.id is not None}
    filtered_outcomes = [
        outcome
        for outcome in outcomes
        if outcome.snapshot_id in ids and (horizon is None or outcome.horizon == horizon)
    ]
    evaluated = [
        outcome
        for outcome in filtered_outcomes
        if outcome.outcome_state in {"win", "loss", "neutral"} and outcome.net_return_pct is not None
    ]
    directional = [
        outcome
        for outcome in evaluated
        if snapshots_by_id[outcome.snapshot_id].direction in {"long", "short"}
    ]
    pending_count = sum(1 for outcome in filtered_outcomes if outcome.outcome_state == "pending")
    if not filtered_outcomes:
        pending_count = len(filtered_snapshots) * (1 if horizon else len(SCANNER_VALIDATION_HORIZONS))

    warnings = _report_warnings(total=len(filtered_snapshots), evaluated=len(directional))
    conclusion = _conclusion(directional)
    return ScannerValidationReport(
        generated_at=datetime.now(tz=UTC),
        total_snapshots=len(filtered_snapshots),
        evaluated_snapshots=len(directional),
        pending_snapshots=pending_count,
        win_rate=_win_rate(directional),
        expectancy=_average_net_return(directional),
        average_win=_average_where(directional, positive=True),
        average_loss=_average_where(directional, positive=False),
        average_net_return=_average_net_return(directional),
        max_drawdown=_max_drawdown(directional),
        scanner_vs_random_baseline=_baseline_comparison(evaluated, snapshots_by_id),
        opportunity_score_bucket_performance=_bucket_performance(directional, snapshots_by_id),
        direction_performance=_group_performance(
            directional,
            snapshots_by_id,
            key=lambda snapshot: snapshot.direction.upper(),
            expected_names=("LONG", "SHORT"),
        ),
        horizon_performance=_group_performance(
            directional,
            snapshots_by_id,
            key=lambda _snapshot, outcome: outcome.horizon,
            expected_names=SCANNER_VALIDATION_HORIZONS,
        ),
        stop_loss_take_profit_analysis=_tp_sl_analysis(directional),
        best_symbols=_ranked_symbol_performance(directional, snapshots_by_id, reverse=True),
        worst_symbols=_ranked_symbol_performance(directional, snapshots_by_id, reverse=False),
        best_regimes=_group_performance(
            directional,
            snapshots_by_id,
            key=lambda snapshot: snapshot.regime_label or "unknown",
        )[:5],
        weak_conditions=_weak_conditions(filtered_snapshots, directional),
        conclusion=conclusion,
        warnings=warnings,
    )


def _snapshot_records_for_group(
    *,
    scan_id: str,
    signals: Sequence[FuturesPaperSignal],
    candidate_group: str,
) -> list[ScannerValidationSnapshotRecord]:
    return [
        ScannerValidationSnapshotRecord(
            id=None,
            scan_id=scan_id,
            symbol=signal.symbol,
            direction=signal.direction,
            price_at_scan=signal.current_price,
            opportunity_score=signal.opportunity_score,
            confidence=signal.confidence,
            horizon=signal.best_horizon,
            risk_grade=signal.risk_grade,
            trend_score=signal.trend_score,
            momentum_score=signal.momentum_score,
            volatility_quality_score=signal.volatility_quality_score,
            liquidity_score=signal.liquidity_score,
            risk_score=signal.risk_score,
            direction_score=signal.direction_score,
            validation_score=signal.validation_score,
            evidence_strength=signal.evidence_strength,
            stop_loss=signal.suggested_stop_loss,
            take_profit=signal.suggested_take_profit,
            timestamp=signal.timestamp,
            rank_position=index,
            candidate_group=candidate_group,
            regime_label=signal.regime,
            data_source=signal.data_source,
        )
        for index, signal in enumerate(signals, start=1)
    ]


def _random_baseline_candidates(
    signals: Sequence[FuturesPaperSignal],
    *,
    scan_id: str,
    sample_size: int,
) -> list[FuturesPaperSignal]:
    if not signals or sample_size <= 0:
        return []
    rng = random.Random(scan_id)
    count = min(sample_size, len(signals))
    return rng.sample(list(signals), count)


def _filter_snapshots(
    *,
    snapshots: Sequence[ScannerValidationSnapshotRecord],
    start_date: date | None,
    end_date: date | None,
    direction: str | None,
    min_opportunity_score: int | None,
    symbol: str | None,
) -> list[ScannerValidationSnapshotRecord]:
    normalized_direction = direction.lower() if direction else None
    normalized_symbol = symbol.upper() if symbol else None
    filtered: list[ScannerValidationSnapshotRecord] = []
    for snapshot in snapshots:
        if normalized_symbol is not None and snapshot.symbol.upper() != normalized_symbol:
            continue
        if normalized_direction is not None and snapshot.direction != normalized_direction:
            continue
        if min_opportunity_score is not None and snapshot.opportunity_score < min_opportunity_score:
            continue
        if start_date is not None and snapshot.timestamp.date() < start_date:
            continue
        if end_date is not None and snapshot.timestamp.date() > end_date:
            continue
        filtered.append(snapshot)
    return filtered


def _load_outcome_candles(
    repository: StorageRepository,
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[HistoricalCandleRecord]:
    lookback_start = start - timedelta(minutes=1)
    lookahead_end = end + timedelta(hours=1)
    for interval in ("15m", "1h", "1m"):
        candles = repository.get_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=lookback_start,
            end_time=lookahead_end,
        )
        if candles and any(candle.close_time >= end for candle in candles):
            return candles
    return []


def _horizon_delta(horizon: str) -> timedelta:
    return {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "24h": timedelta(hours=24),
    }[horizon]


def _pending_outcome(
    *,
    snapshot: ScannerValidationSnapshotRecord,
    horizon: str,
    evaluated_at: datetime,
) -> ScannerValidationOutcomeRecord:
    return ScannerValidationOutcomeRecord(
        id=None,
        snapshot_id=snapshot.id or 0,
        horizon=horizon,
        future_price=None,
        gross_return_pct=None,
        estimated_fee_pct=ESTIMATED_FEE_PCT,
        estimated_slippage_pct=ESTIMATED_SLIPPAGE_PCT,
        net_return_pct=None,
        direction_correct=None,
        max_favorable_move_pct=None,
        max_adverse_move_pct=None,
        take_profit_hit=False,
        stop_loss_hit=False,
        first_exit=None,
        outcome_state="pending",
        evaluated_at=evaluated_at,
    )


def _insufficient_outcome(
    *,
    snapshot: ScannerValidationSnapshotRecord,
    horizon: str,
    evaluated_at: datetime,
) -> ScannerValidationOutcomeRecord:
    outcome = _pending_outcome(snapshot=snapshot, horizon=horizon, evaluated_at=evaluated_at)
    outcome.outcome_state = "insufficient_data"
    return outcome


def _gross_return_pct(
    *,
    direction: str,
    entry_price: Decimal,
    future_price: Decimal,
) -> Decimal | None:
    if direction == "long":
        return ((future_price - entry_price) / entry_price) * Decimal("100")
    if direction == "short":
        return ((entry_price - future_price) / entry_price) * Decimal("100")
    return None


def _favorable_adverse_moves(
    *,
    direction: str,
    entry_price: Decimal,
    candles: Sequence[HistoricalCandleRecord],
) -> tuple[Decimal | None, Decimal | None]:
    if direction not in {"long", "short"} or not candles:
        return None, None
    highs = [candle.high_price for candle in candles]
    lows = [candle.low_price for candle in candles]
    if direction == "long":
        favorable = ((max(highs) - entry_price) / entry_price) * Decimal("100")
        adverse = ((min(lows) - entry_price) / entry_price) * Decimal("100")
    else:
        favorable = ((entry_price - min(lows)) / entry_price) * Decimal("100")
        adverse = ((entry_price - max(highs)) / entry_price) * Decimal("100")
    return _quantize_pct(favorable), _quantize_pct(adverse)


def _tp_sl_state(
    *,
    snapshot: ScannerValidationSnapshotRecord,
    candles: Sequence[HistoricalCandleRecord],
) -> tuple[bool, bool, str | None]:
    if snapshot.direction not in {"long", "short"}:
        return False, False, None
    tp_hit = False
    sl_hit = False
    first_exit: str | None = None
    for candle in candles:
        if snapshot.direction == "long":
            candle_tp = snapshot.take_profit is not None and candle.high_price >= snapshot.take_profit
            candle_sl = snapshot.stop_loss is not None and candle.low_price <= snapshot.stop_loss
        else:
            candle_tp = snapshot.take_profit is not None and candle.low_price <= snapshot.take_profit
            candle_sl = snapshot.stop_loss is not None and candle.high_price >= snapshot.stop_loss
        tp_hit = tp_hit or candle_tp
        sl_hit = sl_hit or candle_sl
        if first_exit is None:
            if candle_tp and candle_sl:
                first_exit = "both_same_candle"
            elif candle_tp:
                first_exit = "take_profit"
            elif candle_sl:
                first_exit = "stop_loss"
    return tp_hit, sl_hit, first_exit


def _bucket_performance(
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    snapshots_by_id: dict[int | None, ScannerValidationSnapshotRecord],
) -> list[ScannerValidationGroupPerformance]:
    buckets = {
        "60-70": lambda score: 60 <= score < 70,
        "70-80": lambda score: 70 <= score < 80,
        "80-90": lambda score: 80 <= score < 90,
        "90+": lambda score: score >= 90,
    }
    return [
        _metric_for_group(
            name=name,
            outcomes=[
                outcome
                for outcome in outcomes
                if predicate(snapshots_by_id[outcome.snapshot_id].opportunity_score)
            ],
        )
        for name, predicate in buckets.items()
    ]


def _group_performance(
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    snapshots_by_id: dict[int | None, ScannerValidationSnapshotRecord],
    *,
    key,
    expected_names: Sequence[str] = (),
) -> list[ScannerValidationGroupPerformance]:
    grouped: dict[str, list[ScannerValidationOutcomeRecord]] = defaultdict(list)
    for outcome in outcomes:
        snapshot = snapshots_by_id[outcome.snapshot_id]
        try:
            group_name = key(snapshot, outcome)
        except TypeError:
            group_name = key(snapshot)
        grouped[str(group_name)].append(outcome)
    names = list(dict.fromkeys((*expected_names, *sorted(grouped))))
    return [_metric_for_group(name=name, outcomes=grouped.get(name, [])) for name in names]


def _ranked_symbol_performance(
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    snapshots_by_id: dict[int | None, ScannerValidationSnapshotRecord],
    *,
    reverse: bool,
) -> list[ScannerValidationGroupPerformance]:
    groups = _group_performance(outcomes, snapshots_by_id, key=lambda snapshot: snapshot.symbol)
    groups = [group for group in groups if group.sample_size > 0 and group.average_net_return is not None]
    return sorted(groups, key=lambda item: item.average_net_return or Decimal("0"), reverse=reverse)[:5]


def _baseline_comparison(
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    snapshots_by_id: dict[int | None, ScannerValidationSnapshotRecord],
) -> ScannerBaselineComparison:
    scanner = [
        outcome
        for outcome in outcomes
        if snapshots_by_id[outcome.snapshot_id].candidate_group in {"top_long", "top_short"}
    ]
    random_baseline = [
        outcome
        for outcome in outcomes
        if snapshots_by_id[outcome.snapshot_id].candidate_group == "random_baseline"
    ]
    scanner_avg = _average_net_return(scanner)
    baseline_avg = _average_net_return(random_baseline)
    return ScannerBaselineComparison(
        scanner_sample_size=len(scanner),
        random_baseline_sample_size=len(random_baseline),
        scanner_average_net_return=scanner_avg,
        random_baseline_average_net_return=baseline_avg,
        scanner_win_rate=_win_rate(scanner),
        random_baseline_win_rate=_win_rate(random_baseline),
        edge_vs_random=(
            _quantize_pct(scanner_avg - baseline_avg)
            if scanner_avg is not None and baseline_avg is not None
            else None
        ),
    )


def _tp_sl_analysis(outcomes: Sequence[ScannerValidationOutcomeRecord]) -> StopLossTakeProfitAnalysis:
    sample_size = len(outcomes)
    tp_count = sum(1 for outcome in outcomes if outcome.take_profit_hit)
    sl_count = sum(1 for outcome in outcomes if outcome.stop_loss_hit)
    neither = sample_size - sum(1 for outcome in outcomes if outcome.take_profit_hit or outcome.stop_loss_hit)
    return StopLossTakeProfitAnalysis(
        sample_size=sample_size,
        take_profit_hit_rate=_rate(tp_count, sample_size),
        stop_loss_hit_rate=_rate(sl_count, sample_size),
        neither_hit_rate=_rate(neither, sample_size),
        take_profit_first=sum(1 for outcome in outcomes if outcome.first_exit == "take_profit"),
        stop_loss_first=sum(1 for outcome in outcomes if outcome.first_exit == "stop_loss"),
    )


def _metric_for_group(
    *,
    name: str,
    outcomes: Sequence[ScannerValidationOutcomeRecord],
) -> ScannerValidationGroupPerformance:
    return ScannerValidationGroupPerformance(
        name=name,
        sample_size=len(outcomes),
        win_rate=_win_rate(outcomes),
        average_net_return=_average_net_return(outcomes),
        expectancy=_average_net_return(outcomes),
    )


def _win_rate(outcomes: Sequence[ScannerValidationOutcomeRecord]) -> Decimal | None:
    if not outcomes:
        return None
    wins = sum(1 for outcome in outcomes if outcome.outcome_state == "win")
    return _rate(wins, len(outcomes))


def _rate(count: int, total: int) -> Decimal | None:
    if total <= 0:
        return None
    return _quantize_pct((Decimal(count) / Decimal(total)) * Decimal("100"))


def _average_net_return(outcomes: Sequence[ScannerValidationOutcomeRecord]) -> Decimal | None:
    values = [outcome.net_return_pct for outcome in outcomes if outcome.net_return_pct is not None]
    if not values:
        return None
    return _quantize_pct(sum(values, start=Decimal("0")) / Decimal(len(values)))


def _average_where(
    outcomes: Sequence[ScannerValidationOutcomeRecord],
    *,
    positive: bool,
) -> Decimal | None:
    values = [
        outcome.net_return_pct
        for outcome in outcomes
        if outcome.net_return_pct is not None
        and ((positive and outcome.net_return_pct > Decimal("0")) or (not positive and outcome.net_return_pct < Decimal("0")))
    ]
    if not values:
        return None
    return _quantize_pct(sum(values, start=Decimal("0")) / Decimal(len(values)))


def _max_drawdown(outcomes: Sequence[ScannerValidationOutcomeRecord]) -> Decimal | None:
    values = [outcome.net_return_pct for outcome in outcomes if outcome.net_return_pct is not None]
    if not values:
        return None
    equity = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return _quantize_pct(drawdown)


def _weak_conditions(
    snapshots: Sequence[ScannerValidationSnapshotRecord],
    outcomes: Sequence[ScannerValidationOutcomeRecord],
) -> list[str]:
    conditions: list[str] = []
    if len(outcomes) < MIN_REPORT_SAMPLE_SIZE:
        conditions.append("not enough data: scanner validation sample is still small")
    weak_count = sum(
        1
        for snapshot in snapshots
        if snapshot.evidence_strength in {"insufficient", "unvalidated", "weak"}
    )
    if snapshots and weak_count / len(snapshots) >= 0.5:
        conditions.append("many scanner signals are weakly validated or unvalidated")
    if any(snapshot.candidate_group == "random_baseline" for snapshot in snapshots) and not outcomes:
        conditions.append("random baseline exists but has not matured for evaluation yet")
    return conditions


def _report_warnings(*, total: int, evaluated: int) -> list[str]:
    warnings = [
        "Paper validation only. Results use estimated net return and do not prove live profitability.",
    ]
    if total == 0:
        warnings.append("No scanner snapshots have been stored yet.")
    if evaluated < MIN_REPORT_SAMPLE_SIZE:
        warnings.append("not enough data: use this report as an early validation read only.")
    return warnings


def _conclusion(outcomes: Sequence[ScannerValidationOutcomeRecord]) -> str:
    if len(outcomes) < MIN_REPORT_SAMPLE_SIZE:
        return "insufficient_data"
    expectancy = _average_net_return(outcomes) or Decimal("0")
    win_rate = _win_rate(outcomes) or Decimal("0")
    if expectancy >= Decimal("0.30") and win_rate >= Decimal("60"):
        return "strong"
    if expectancy >= Decimal("0.10") and win_rate >= Decimal("52"):
        return "promising"
    if expectancy > Decimal("0") or win_rate >= Decimal("48"):
        return "mixed"
    return "weak"


def _quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _materialized_ids(records: Iterable[ScannerValidationSnapshotRecord]) -> list[int]:
    return [record.id for record in records if record.id is not None]
