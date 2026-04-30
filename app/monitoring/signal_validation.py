"""Signal profitability validation and edge-discovery analytics."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.storage.models import HistoricalCandleRecord, SignalValidationSnapshotRecord


VALIDATION_HORIZONS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}
MIN_REPORT_SAMPLES = 5
DEFAULT_COST_PCT = Decimal("0.20")


@dataclass(slots=True)
class SignalOutcome:
    """Forward outcome for one signal and horizon."""

    signal_id: int | None
    symbol: str
    timestamp: object
    horizon: str
    action: str
    risk_grade: str
    confidence: int
    confidence_bucket: str
    baseline_price: Decimal
    future_price: Decimal
    price_return_pct: Decimal
    directional_return_pct: Decimal | None
    direction_correct: bool | None
    max_favorable_move_pct: Decimal
    max_adverse_move_pct: Decimal
    invalidation_hit: bool
    survived_fees_slippage: bool
    actionable_or_noise: str
    trade_opened: bool
    ignored_or_blocked: bool
    blocker_reasons: tuple[str, ...]
    top_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    technical_score: Decimal | None
    sentiment_score: Decimal | None
    pattern_score: Decimal | None


@dataclass(slots=True)
class HorizonQualityMetric:
    """Aggregated signal-quality metrics for one forward horizon."""

    horizon: str
    sample_size: int
    actionable_sample_size: int
    win_rate_pct: Decimal | None
    expectancy_pct: Decimal | None
    average_favorable_move_pct: Decimal | None
    average_adverse_move_pct: Decimal | None
    false_positive_rate_pct: Decimal | None
    false_breakout_rate_pct: Decimal | None
    winner_average_confidence: Decimal | None
    loser_average_confidence: Decimal | None


@dataclass(slots=True)
class GroupPerformanceMetric:
    """Performance metrics for a categorical signal group."""

    name: str
    sample_size: int
    win_rate_pct: Decimal | None
    expectancy_pct: Decimal | None


@dataclass(slots=True)
class ReasonPerformanceMetric:
    """Measured usefulness of one reason or blocker."""

    reason: str
    sample_size: int
    win_rate_pct: Decimal | None
    expectancy_pct: Decimal | None


@dataclass(slots=True)
class SignalValidationReport:
    """Complete signal-validation analytics response."""

    symbol: str | None
    start_date: object | None
    end_date: object | None
    status: Literal["ready", "insufficient_data"]
    status_message: str | None
    total_signals: int
    actionable_signals: int
    ignored_or_blocked_signals: int
    horizons: list[HorizonQualityMetric]
    performance_by_action: list[GroupPerformanceMetric]
    performance_by_risk_grade: list[GroupPerformanceMetric]
    performance_by_confidence_bucket: list[GroupPerformanceMetric]
    performance_by_symbol: list[GroupPerformanceMetric]


@dataclass(slots=True)
class EdgeReport:
    """Evidence-based edge discovery report."""

    symbol: str | None
    start_date: object | None
    end_date: object | None
    status: Literal["ready", "insufficient_data"]
    status_message: str | None
    useful_symbols: list[GroupPerformanceMetric] = field(default_factory=list)
    weak_symbols: list[GroupPerformanceMetric] = field(default_factory=list)
    best_horizons: list[HorizonQualityMetric] = field(default_factory=list)
    reliable_confidence_ranges: list[GroupPerformanceMetric] = field(default_factory=list)
    risk_grades_to_avoid: list[GroupPerformanceMetric] = field(default_factory=list)
    useful_reasons: list[ReasonPerformanceMetric] = field(default_factory=list)
    noisy_reasons: list[ReasonPerformanceMetric] = field(default_factory=list)
    protective_blockers: list[ReasonPerformanceMetric] = field(default_factory=list)
    noisy_modules: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ModuleAttributionReport:
    """Measured module-level correlation with profitable outcomes."""

    symbol: str | None
    start_date: object | None
    end_date: object | None
    status: Literal["ready", "insufficient_data"]
    status_message: str | None
    modules: list[GroupPerformanceMetric]


def build_signal_validation_report(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
    symbol: str | None,
    start_date,
    end_date,
    horizon: str | None = None,
) -> SignalValidationReport:
    """Build signal-quality metrics from persisted snapshots and forward candles."""

    outcomes = evaluate_signal_outcomes(snapshots=snapshots, candles_by_symbol=candles_by_symbol)
    if horizon is not None:
        outcomes = [item for item in outcomes if item.horizon == horizon]
    horizons = [_build_horizon_metric(name, [item for item in outcomes if item.horizon == name]) for name in _selected_horizons(horizon)]
    actionable_signals = sum(1 for item in snapshots if _is_actionable(item))
    blocked_signals = sum(1 for item in snapshots if item.signal_ignored_or_blocked)
    status = "ready" if outcomes else "insufficient_data"
    return SignalValidationReport(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        status=status,
        status_message=None if status == "ready" else "Not enough forward candle data exists to evaluate stored signals yet.",
        total_signals=len(snapshots),
        actionable_signals=actionable_signals,
        ignored_or_blocked_signals=blocked_signals,
        horizons=horizons,
        performance_by_action=_group_metrics(outcomes, lambda item: item.action),
        performance_by_risk_grade=_group_metrics(outcomes, lambda item: item.risk_grade),
        performance_by_confidence_bucket=_group_metrics(outcomes, lambda item: item.confidence_bucket),
        performance_by_symbol=_group_metrics(outcomes, lambda item: item.symbol),
    )


def build_edge_report(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
    symbol: str | None,
    start_date,
    end_date,
    horizon: str | None = None,
) -> EdgeReport:
    """Summarize where measured signal edge appears or fails."""

    outcomes = evaluate_signal_outcomes(snapshots=snapshots, candles_by_symbol=candles_by_symbol)
    if horizon is not None:
        outcomes = [item for item in outcomes if item.horizon == horizon]
    directional = [item for item in outcomes if item.directional_return_pct is not None]
    if len(directional) < MIN_REPORT_SAMPLES:
        return EdgeReport(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            status="insufficient_data",
            status_message=(
                f"Need at least {MIN_REPORT_SAMPLES} evaluated directional outcomes before making edge conclusions."
            ),
        )

    symbol_metrics = _group_metrics(directional, lambda item: item.symbol)
    confidence_metrics = _group_metrics(directional, lambda item: item.confidence_bucket)
    risk_metrics = _group_metrics(directional, lambda item: item.risk_grade)
    horizon_metrics = [_build_horizon_metric(name, [item for item in directional if item.horizon == name]) for name in _selected_horizons(horizon)]
    reason_metrics = _reason_metrics(directional)
    blocker_metrics = _blocker_metrics(outcomes)
    noisy_modules = _noisy_modules(directional)
    return EdgeReport(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        status="ready",
        status_message=None,
        useful_symbols=[item for item in symbol_metrics if _positive_edge(item)],
        weak_symbols=[item for item in symbol_metrics if _negative_edge(item)],
        best_horizons=[item for item in horizon_metrics if item.expectancy_pct is not None and item.expectancy_pct > 0],
        reliable_confidence_ranges=[item for item in confidence_metrics if _positive_edge(item)],
        risk_grades_to_avoid=[item for item in risk_metrics if _negative_edge(item)],
        useful_reasons=[item for item in reason_metrics if _positive_edge(item)],
        noisy_reasons=[item for item in reason_metrics if _negative_edge(item)],
        protective_blockers=[item for item in blocker_metrics if item.expectancy_pct is not None and item.expectancy_pct < 0],
        noisy_modules=noisy_modules,
        suggestions=_suggestions(
            confidence_metrics=confidence_metrics,
            risk_metrics=risk_metrics,
            horizon_metrics=horizon_metrics,
            symbol_metrics=symbol_metrics,
            blocker_metrics=blocker_metrics,
            noisy_modules=noisy_modules,
        ),
    )


def build_module_attribution_report(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
    symbol: str | None,
    start_date,
    end_date,
    horizon: str | None = None,
) -> ModuleAttributionReport:
    """Return deterministic module attribution from measured outcomes."""

    outcomes = evaluate_signal_outcomes(snapshots=snapshots, candles_by_symbol=candles_by_symbol)
    if horizon is not None:
        outcomes = [item for item in outcomes if item.horizon == horizon]
    directional = [item for item in outcomes if item.directional_return_pct is not None]
    if len(directional) < MIN_REPORT_SAMPLES:
        return ModuleAttributionReport(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            status="insufficient_data",
            status_message="Not enough evaluated outcomes exist for module attribution.",
            modules=[],
        )
    modules: list[GroupPerformanceMetric] = []
    for module_name, selector in (
        ("technical", lambda item: item.technical_score),
        ("sentiment", lambda item: item.sentiment_score),
        ("pattern", lambda item: item.pattern_score),
        ("ai_advisory", lambda item: Decimal(item.confidence)),
    ):
        active = [item for item in directional if selector(item) is not None]
        metric = _build_group_metric(module_name, active)
        modules.append(metric)
    return ModuleAttributionReport(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        status="ready",
        status_message=None,
        modules=modules,
    )


def evaluate_signal_outcomes(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
) -> list[SignalOutcome]:
    """Evaluate persisted signal snapshots against forward candles."""

    outcomes: list[SignalOutcome] = []
    for snapshot in snapshots:
        candles = candles_by_symbol.get(snapshot.symbol, [])
        if not candles:
            continue
        for horizon, delta in VALIDATION_HORIZONS.items():
            window = [
                candle
                for candle in candles
                if snapshot.timestamp < candle.close_time <= snapshot.timestamp + delta
            ]
            future = next(
                (candle for candle in candles if candle.close_time >= snapshot.timestamp + delta),
                None,
            )
            if future is None:
                continue
            if future not in window:
                window.append(future)
            outcomes.append(_evaluate_one(snapshot, horizon, future, window))
    return outcomes


def _evaluate_one(
    snapshot: SignalValidationSnapshotRecord,
    horizon: str,
    future: HistoricalCandleRecord,
    window: list[HistoricalCandleRecord],
) -> SignalOutcome:
    direction = _action_direction(snapshot)
    price_return_pct = _pct_return(snapshot.price, future.close_price)
    high = max((candle.high_price for candle in window), default=future.high_price)
    low = min((candle.low_price for candle in window), default=future.low_price)
    if direction == 1:
        directional_return = price_return_pct
        max_favorable = _pct_return(snapshot.price, high)
        max_adverse = _pct_return(snapshot.price, low)
    elif direction == -1:
        directional_return = -price_return_pct
        max_favorable = -_pct_return(snapshot.price, low)
        max_adverse = -_pct_return(snapshot.price, high)
    else:
        directional_return = None
        max_favorable = abs(price_return_pct)
        max_adverse = Decimal("0")
    cost = snapshot.estimated_cost_pct if snapshot.estimated_cost_pct is not None else DEFAULT_COST_PCT
    direction_correct = directional_return > Decimal("0") if directional_return is not None else None
    survived = directional_return is not None and directional_return > cost
    noise = _actionable_or_noise(snapshot, directional_return, cost)
    return SignalOutcome(
        signal_id=snapshot.id,
        symbol=snapshot.symbol,
        timestamp=snapshot.timestamp,
        horizon=horizon,
        action=snapshot.final_action,
        risk_grade=snapshot.risk_grade,
        confidence=snapshot.confidence,
        confidence_bucket=_confidence_bucket(snapshot.confidence),
        baseline_price=snapshot.price,
        future_price=future.close_price,
        price_return_pct=_q(price_return_pct),
        directional_return_pct=_q(directional_return) if directional_return is not None else None,
        direction_correct=direction_correct,
        max_favorable_move_pct=_q(max(Decimal("0"), max_favorable)),
        max_adverse_move_pct=_q(min(Decimal("0"), max_adverse)),
        invalidation_hit=_invalidation_hit(snapshot, high=high, low=low),
        survived_fees_slippage=survived,
        actionable_or_noise=noise,
        trade_opened=snapshot.trade_opened,
        ignored_or_blocked=snapshot.signal_ignored_or_blocked,
        blocker_reasons=snapshot.blocker_reasons,
        top_reasons=snapshot.top_reasons,
        warnings=snapshot.warnings,
        technical_score=snapshot.technical_score,
        sentiment_score=snapshot.sentiment_score,
        pattern_score=snapshot.pattern_score,
    )


def _build_horizon_metric(horizon: str, outcomes: list[SignalOutcome]) -> HorizonQualityMetric:
    directional = [item for item in outcomes if item.directional_return_pct is not None]
    wins = [item for item in directional if item.survived_fees_slippage]
    losses = [item for item in directional if not item.survived_fees_slippage]
    breakout = [item for item in directional if any("breakout" in reason.lower() for reason in item.top_reasons)]
    false_breakout = [item for item in breakout if not item.survived_fees_slippage]
    return HorizonQualityMetric(
        horizon=horizon,
        sample_size=len(outcomes),
        actionable_sample_size=len(directional),
        win_rate_pct=_rate(len(wins), len(directional)),
        expectancy_pct=_avg([item.directional_return_pct for item in directional if item.directional_return_pct is not None]),
        average_favorable_move_pct=_avg([item.max_favorable_move_pct for item in outcomes]),
        average_adverse_move_pct=_avg([item.max_adverse_move_pct for item in outcomes]),
        false_positive_rate_pct=_rate(len(losses), len(directional)),
        false_breakout_rate_pct=_rate(len(false_breakout), len(breakout)),
        winner_average_confidence=_avg([Decimal(item.confidence) for item in wins]),
        loser_average_confidence=_avg([Decimal(item.confidence) for item in losses]),
    )


def _group_metrics(outcomes: list[SignalOutcome], key_selector) -> list[GroupPerformanceMetric]:
    groups: dict[str, list[SignalOutcome]] = defaultdict(list)
    for item in outcomes:
        groups[str(key_selector(item))].append(item)
    return sorted(
        (_build_group_metric(name, group) for name, group in groups.items()),
        key=lambda item: (-item.sample_size, item.name),
    )


def _build_group_metric(name: str, outcomes: list[SignalOutcome]) -> GroupPerformanceMetric:
    directional = [item for item in outcomes if item.directional_return_pct is not None]
    wins = [item for item in directional if item.survived_fees_slippage]
    return GroupPerformanceMetric(
        name=name,
        sample_size=len(outcomes),
        win_rate_pct=_rate(len(wins), len(directional)),
        expectancy_pct=_avg([item.directional_return_pct for item in directional if item.directional_return_pct is not None]),
    )


def _reason_metrics(outcomes: list[SignalOutcome]) -> list[ReasonPerformanceMetric]:
    groups: dict[str, list[SignalOutcome]] = defaultdict(list)
    for item in outcomes:
        for reason in item.top_reasons:
            groups[reason].append(item)
    return _reason_metric_list(groups)


def _blocker_metrics(outcomes: list[SignalOutcome]) -> list[ReasonPerformanceMetric]:
    groups: dict[str, list[SignalOutcome]] = defaultdict(list)
    for item in outcomes:
        for reason in item.blocker_reasons:
            groups[reason].append(item)
    return _reason_metric_list(groups)


def _reason_metric_list(groups: dict[str, list[SignalOutcome]]) -> list[ReasonPerformanceMetric]:
    metrics = []
    for reason, items in groups.items():
        directional = [item for item in items if item.directional_return_pct is not None]
        wins = [item for item in directional if item.survived_fees_slippage]
        metrics.append(
            ReasonPerformanceMetric(
                reason=reason,
                sample_size=len(items),
                win_rate_pct=_rate(len(wins), len(directional)),
                expectancy_pct=_avg([item.directional_return_pct for item in directional if item.directional_return_pct is not None]),
            )
        )
    return sorted(metrics, key=lambda item: (item.expectancy_pct or Decimal("-999"), item.sample_size), reverse=True)


def _noisy_modules(outcomes: list[SignalOutcome]) -> list[str]:
    noisy: list[str] = []
    for name, attr in (
        ("technical", "technical_score"),
        ("sentiment", "sentiment_score"),
        ("pattern", "pattern_score"),
    ):
        active = [item for item in outcomes if getattr(item, attr) is not None]
        metric = _build_group_metric(name, active)
        if _negative_edge(metric):
            noisy.append(name)
    return noisy


def _suggestions(
    *,
    confidence_metrics: list[GroupPerformanceMetric],
    risk_metrics: list[GroupPerformanceMetric],
    horizon_metrics: list[HorizonQualityMetric],
    symbol_metrics: list[GroupPerformanceMetric],
    blocker_metrics: list[ReasonPerformanceMetric],
    noisy_modules: list[str],
) -> list[str]:
    suggestions: list[str] = []
    low_conf = next((item for item in confidence_metrics if item.name == "low"), None)
    high_conf = next((item for item in confidence_metrics if item.name == "high"), None)
    if low_conf is not None and _negative_edge(low_conf):
        suggestions.append("Raise minimum confidence before taking paper entries; low-confidence signals are losing after costs.")
    if high_conf is not None and _positive_edge(high_conf):
        suggestions.append("Prioritize high-confidence signals; this bucket is showing positive expectancy after costs.")
    for risk in risk_metrics:
        if risk.name == "high" and _negative_edge(risk):
            suggestions.append("Avoid high-risk-grade entries until the validation sample improves.")
    positive_horizons = [item for item in horizon_metrics if item.expectancy_pct is not None and item.expectancy_pct > 0]
    if positive_horizons:
        best = max(positive_horizons, key=lambda item: item.expectancy_pct or Decimal("0"))
        suggestions.append(f"Prefer the {best.horizon} validation horizon; it currently has the strongest measured expectancy.")
    for symbol in symbol_metrics:
        if _negative_edge(symbol):
            suggestions.append(f"Reduce or pause paper entries for {symbol.name}; measured signal expectancy is negative.")
    for blocker in blocker_metrics:
        if blocker.expectancy_pct is not None and blocker.expectancy_pct > 0 and blocker.sample_size >= MIN_REPORT_SAMPLES:
            suggestions.append(f"Review blocker '{blocker.reason}'; blocked signals later performed well in the sample.")
        elif blocker.expectancy_pct is not None and blocker.expectancy_pct < 0 and blocker.sample_size >= MIN_REPORT_SAMPLES:
            suggestions.append(f"Keep blocker '{blocker.reason}'; it is filtering signals that later performed poorly.")
    for module_name in noisy_modules:
        suggestions.append(f"Reduce reliance on the {module_name} layer until it correlates better with winners.")
    return list(dict.fromkeys(suggestions))


def _action_direction(snapshot: SignalValidationSnapshotRecord) -> int:
    if snapshot.final_action == "buy":
        return 1
    if snapshot.final_action == "sell_exit":
        return -1
    if snapshot.signal_ignored_or_blocked and snapshot.fusion_final_signal == "long":
        return 1
    if snapshot.signal_ignored_or_blocked and snapshot.fusion_final_signal in {"short", "exit_short", "reduce_risk"}:
        return -1
    if snapshot.final_action == "avoid" and snapshot.fusion_final_signal in {"short", "exit_short", "reduce_risk"}:
        return -1
    return 0


def _is_actionable(snapshot: SignalValidationSnapshotRecord) -> bool:
    return snapshot.final_action in {"buy", "sell_exit"} and not snapshot.signal_ignored_or_blocked


def _actionable_or_noise(
    snapshot: SignalValidationSnapshotRecord,
    directional_return: Decimal | None,
    cost: Decimal,
) -> str:
    if directional_return is None:
        return "noise" if abs(snapshot.expected_edge_pct or Decimal("0")) <= cost else "not_actionable"
    return "actionable" if directional_return > cost else "noise"


def _confidence_bucket(confidence: int) -> str:
    if confidence >= 70:
        return "high"
    if confidence >= 45:
        return "medium"
    return "low"


def _selected_horizons(horizon: str | None) -> list[str]:
    return [horizon] if horizon in VALIDATION_HORIZONS else list(VALIDATION_HORIZONS.keys())


def _pct_return(start: Decimal, end: Decimal) -> Decimal:
    if start <= Decimal("0"):
        return Decimal("0")
    return ((end - start) / start) * Decimal("100")


def _invalidation_hit(snapshot: SignalValidationSnapshotRecord, *, high: Decimal, low: Decimal) -> bool:
    if not snapshot.invalidation_hint:
        return False
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", snapshot.invalidation_hint)
    if match is None:
        return False
    level = Decimal(match.group(1))
    direction = _action_direction(snapshot)
    if direction == 1:
        return low <= level
    if direction == -1:
        return high >= level
    return False


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator <= 0:
        return None
    return _q((Decimal(numerator) / Decimal(denominator)) * Decimal("100"))


def _avg(values: list[Decimal | None]) -> Decimal | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return _q(sum(clean, start=Decimal("0")) / Decimal(len(clean)))


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _positive_edge(item) -> bool:
    return (
        item.sample_size >= MIN_REPORT_SAMPLES
        and item.expectancy_pct is not None
        and item.expectancy_pct > Decimal("0")
        and (item.win_rate_pct is None or item.win_rate_pct >= Decimal("45"))
    )


def _negative_edge(item) -> bool:
    return (
        item.sample_size >= MIN_REPORT_SAMPLES
        and item.expectancy_pct is not None
        and item.expectancy_pct < Decimal("0")
    )
