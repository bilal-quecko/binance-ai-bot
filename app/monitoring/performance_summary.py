"""Aggregated post-signal performance summary metrics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.storage.models import SignalOutcomeRecord, SignalOutcomeSnapshotRecord


@dataclass(slots=True, frozen=True)
class PostSignalGroupSummary:
    """Aggregate outcome metrics for one segment."""

    name: str
    total_signals: int
    evaluated_signals: int
    win_rate: Decimal | None
    avg_return: Decimal | None
    avg_max_upside: Decimal | None
    avg_max_drawdown: Decimal | None
    tp_hit_rate: Decimal | None
    sl_hit_rate: Decimal | None


@dataclass(slots=True, frozen=True)
class PostSignalPerformanceSummary:
    """Full post-signal performance summary."""

    generated_at: datetime
    total_signals: int
    evaluated_signals: int
    win_rate: Decimal | None
    avg_return: Decimal | None
    avg_max_upside: Decimal | None
    avg_max_drawdown: Decimal | None
    tp_hit_rate: Decimal | None
    sl_hit_rate: Decimal | None
    base_win_rate: Decimal | None = None
    heatmap_win_rate: Decimal | None = None
    delta_win_rate: Decimal | None = None
    base_avg_return: Decimal | None = None
    heatmap_avg_return: Decimal | None = None
    heatmap_accuracy_on_sweep_prediction: Decimal | None = None
    heatmap_false_signal_rate: Decimal | None = None
    heatmap_signal_count_by_data_quality: dict[str, int] = field(default_factory=dict)
    win_rate_by_heatmap_data_quality: dict[str, Decimal | None] = field(default_factory=dict)
    sweep_accuracy_by_data_quality: dict[str, Decimal | None] = field(default_factory=dict)
    avg_return_by_data_quality: dict[str, Decimal | None] = field(default_factory=dict)
    by_signal_type: list[PostSignalGroupSummary] = field(default_factory=list)
    by_confidence_bucket: list[PostSignalGroupSummary] = field(default_factory=list)
    by_liquidity_bias: list[PostSignalGroupSummary] = field(default_factory=list)
    by_source: list[PostSignalGroupSummary] = field(default_factory=list)


def build_post_signal_performance_summary(
    *,
    snapshots: Sequence[SignalOutcomeSnapshotRecord],
    outcomes: Sequence[SignalOutcomeRecord],
    horizon: str = "15m",
) -> PostSignalPerformanceSummary:
    """Build deterministic aggregate metrics from stored post-signal outcomes."""

    latest_outcomes = _latest_outcomes_by_signal(outcomes=outcomes, horizon=horizon)
    outcomes_by_id = latest_outcomes
    snapshot_by_id = {snapshot.id: snapshot for snapshot in snapshots}
    base_win_rate = _bool_rate(
        [outcome.base_signal_correct for outcome in outcomes_by_id.values() if outcome.base_signal_correct is not None]
    )
    heatmap_win_rate = _bool_rate(
        [
            outcome.heatmap_signal_correct
            for outcome in outcomes_by_id.values()
            if outcome.heatmap_signal_correct is not None
        ]
    )
    return PostSignalPerformanceSummary(
        generated_at=datetime.now(tz=UTC),
        total_signals=len(snapshots),
        evaluated_signals=sum(1 for snapshot in snapshots if outcomes_by_id.get(snapshot.id) is not None),
        win_rate=_win_rate(outcomes_by_id.values()),
        avg_return=_average([outcome.price_change_percent for outcome in outcomes_by_id.values()]),
        avg_max_upside=_average([outcome.max_upside_percent for outcome in outcomes_by_id.values()]),
        avg_max_drawdown=_average([outcome.max_downside_percent for outcome in outcomes_by_id.values()]),
        tp_hit_rate=_hit_rate([outcome.did_price_hit_tp for outcome in outcomes_by_id.values()]),
        sl_hit_rate=_hit_rate([outcome.did_price_hit_sl for outcome in outcomes_by_id.values()]),
        base_win_rate=base_win_rate,
        heatmap_win_rate=heatmap_win_rate,
        delta_win_rate=(
            (heatmap_win_rate - base_win_rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if base_win_rate is not None and heatmap_win_rate is not None
            else None
        ),
        base_avg_return=_average(
            [
                _directional_return(snapshot_by_id[outcome.signal_id].base_signal_type or snapshot_by_id[outcome.signal_id].signal_type, outcome.price_change_percent)
                for outcome in outcomes_by_id.values()
                if outcome.signal_id in snapshot_by_id
            ]
        ),
        heatmap_avg_return=_average(
            [
                _directional_return(
                    snapshot_by_id[outcome.signal_id].heatmap_signal_type
                    or snapshot_by_id[outcome.signal_id].base_signal_type
                    or snapshot_by_id[outcome.signal_id].signal_type,
                    outcome.price_change_percent,
                )
                for outcome in outcomes_by_id.values()
                if outcome.signal_id in snapshot_by_id
            ]
        ),
        heatmap_accuracy_on_sweep_prediction=_bool_rate(
            [
                outcome.sweep_prediction_correct
                for outcome in outcomes_by_id.values()
                if outcome.sweep_prediction_correct is not None
            ]
        ),
        heatmap_false_signal_rate=_heatmap_false_signal_rate(
            snapshots=snapshot_by_id,
            outcomes=outcomes_by_id.values(),
        ),
        heatmap_signal_count_by_data_quality=_signal_count_by_data_quality(snapshots),
        win_rate_by_heatmap_data_quality=_quality_metric(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            metric=lambda item_outcomes: _bool_rate(
                [
                    outcome.heatmap_signal_correct
                    for outcome in item_outcomes
                    if outcome.heatmap_signal_correct is not None
                ]
            ),
        ),
        sweep_accuracy_by_data_quality=_quality_metric(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            metric=lambda item_outcomes: _bool_rate(
                [
                    outcome.sweep_prediction_correct
                    for outcome in item_outcomes
                    if outcome.sweep_prediction_correct is not None
                ]
            ),
        ),
        avg_return_by_data_quality=_quality_metric(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            metric=lambda item_outcomes: _average([outcome.price_change_percent for outcome in item_outcomes]),
        ),
        by_signal_type=_grouped_summary(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            key=lambda snapshot: snapshot.signal_type,
        ),
        by_confidence_bucket=_grouped_summary(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            key=lambda snapshot: _confidence_bucket(snapshot.confidence),
        ),
        by_liquidity_bias=_grouped_summary(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            key=lambda snapshot: snapshot.liquidity_bias or "none",
        ),
        by_source=_grouped_summary(
            snapshots=snapshots,
            outcomes=outcomes_by_id,
            key=lambda snapshot: snapshot.source,
        ),
    )


def _latest_outcomes_by_signal(
    *,
    outcomes: Sequence[SignalOutcomeRecord],
    horizon: str,
) -> dict[str, SignalOutcomeRecord]:
    selected: dict[str, SignalOutcomeRecord] = {}
    for outcome in outcomes:
        if outcome.horizon != horizon or outcome.outcome_state in {"pending", "insufficient_data"}:
            continue
        previous = selected.get(outcome.signal_id)
        if previous is None or outcome.evaluated_at >= previous.evaluated_at:
            selected[outcome.signal_id] = outcome
    return selected


def _grouped_summary(
    *,
    snapshots: Sequence[SignalOutcomeSnapshotRecord],
    outcomes: dict[str, SignalOutcomeRecord],
    key,
) -> list[PostSignalGroupSummary]:
    grouped: dict[str, list[SignalOutcomeSnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[str(key(snapshot))].append(snapshot)
    summaries: list[PostSignalGroupSummary] = []
    for name, items in grouped.items():
        item_outcomes = [outcomes[item.id] for item in items if item.id in outcomes]
        summaries.append(
            PostSignalGroupSummary(
                name=name,
                total_signals=len(items),
                evaluated_signals=len(item_outcomes),
                win_rate=_win_rate(item_outcomes),
                avg_return=_average([outcome.price_change_percent for outcome in item_outcomes]),
                avg_max_upside=_average([outcome.max_upside_percent for outcome in item_outcomes]),
                avg_max_drawdown=_average([outcome.max_downside_percent for outcome in item_outcomes]),
                tp_hit_rate=_hit_rate([outcome.did_price_hit_tp for outcome in item_outcomes]),
                sl_hit_rate=_hit_rate([outcome.did_price_hit_sl for outcome in item_outcomes]),
            )
        )
    return sorted(summaries, key=lambda item: (-item.evaluated_signals, item.name))


def _confidence_bucket(confidence: int) -> str:
    if confidence < 50:
        return "0-49"
    if confidence < 70:
        return "50-69"
    if confidence < 85:
        return "70-84"
    return "85-100"


def _signal_count_by_data_quality(snapshots: Sequence[SignalOutcomeSnapshotRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for snapshot in snapshots:
        counts[snapshot.heatmap_data_quality or "unknown"] += 1
    return dict(sorted(counts.items()))


def _quality_metric(
    *,
    snapshots: Sequence[SignalOutcomeSnapshotRecord],
    outcomes: dict[str, SignalOutcomeRecord],
    metric,
) -> dict[str, Decimal | None]:
    grouped: dict[str, list[SignalOutcomeRecord]] = defaultdict(list)
    for snapshot in snapshots:
        outcome = outcomes.get(snapshot.id)
        if outcome is not None:
            grouped[snapshot.heatmap_data_quality or "unknown"].append(outcome)
        else:
            grouped.setdefault(snapshot.heatmap_data_quality or "unknown", [])
    return {name: metric(items) for name, items in sorted(grouped.items())}


def _win_rate(outcomes) -> Decimal | None:
    evaluated = [outcome for outcome in outcomes if outcome.direction_correct is not None]
    if not evaluated:
        return None
    wins = sum(1 for outcome in evaluated if outcome.direction_correct)
    return _pct(Decimal(wins), Decimal(len(evaluated)))


def _hit_rate(values: Sequence[bool]) -> Decimal | None:
    if not values:
        return None
    hits = sum(1 for value in values if value)
    return _pct(Decimal(hits), Decimal(len(values)))


def _bool_rate(values: Sequence[bool]) -> Decimal | None:
    if not values:
        return None
    hits = sum(1 for value in values if value)
    return _pct(Decimal(hits), Decimal(len(values)))


def _directional_return(signal_type: str | None, price_change: Decimal | None) -> Decimal | None:
    if price_change is None or signal_type is None:
        return None
    normalized = signal_type.upper()
    if normalized in {"BUY", "LONG"}:
        return price_change
    if normalized in {"SELL", "SHORT", "EXIT", "SELL_EXIT"}:
        return -price_change
    return None


def _heatmap_false_signal_rate(
    *,
    snapshots: dict[str, SignalOutcomeSnapshotRecord],
    outcomes: Sequence[SignalOutcomeRecord],
) -> Decimal | None:
    evaluated: list[SignalOutcomeRecord] = []
    for outcome in outcomes:
        snapshot = snapshots.get(outcome.signal_id)
        if snapshot is None or outcome.heatmap_signal_correct is None:
            continue
        heatmap_signal = (snapshot.heatmap_signal_type or "").upper()
        if heatmap_signal in {"BUY", "SELL", "LONG", "SHORT"}:
            evaluated.append(outcome)
    if not evaluated:
        return None
    misses = sum(1 for outcome in evaluated if outcome.heatmap_signal_correct is False)
    return _pct(Decimal(misses), Decimal(len(evaluated)))


def _average(values: Sequence[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return (sum(present, Decimal("0")) / Decimal(len(present))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= Decimal("0"):
        return Decimal("0.0000")
    return ((numerator / denominator) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
