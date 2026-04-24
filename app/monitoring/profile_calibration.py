"""Profile calibration recommendations from observed paper-trade outcomes."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.storage.models import (
    DrawdownSummary,
    FillRecord,
    PaperSessionRunRecord,
    ProfileTuningSetRecord,
    RunnerEventRecord,
    TradeRecord,
)


PROFILE_ORDER = ("conservative", "balanced", "aggressive")

PROFILE_THRESHOLDS: dict[str, dict[str, Decimal]] = {
    "conservative": {
        "min_atr_ratio": Decimal("0.0008"),
        "max_spread_ratio": Decimal("0.0015"),
        "min_order_book_imbalance": Decimal("-0.20"),
        "min_expected_edge_buffer_pct": Decimal("0.0015"),
        "min_stop_distance_ratio": Decimal("0.0012"),
        "stop_loss_atr_multiple": Decimal("2.2"),
        "take_profit_atr_multiple": Decimal("3.0"),
    },
    "balanced": {
        "min_atr_ratio": Decimal("0.0004"),
        "max_spread_ratio": Decimal("0.0030"),
        "min_order_book_imbalance": Decimal("-0.45"),
        "min_expected_edge_buffer_pct": Decimal("0.0008"),
        "min_stop_distance_ratio": Decimal("0.0008"),
        "stop_loss_atr_multiple": Decimal("1.75"),
        "take_profit_atr_multiple": Decimal("2.4"),
    },
    "aggressive": {
        "min_atr_ratio": Decimal("0.0002"),
        "max_spread_ratio": Decimal("0.0050"),
        "min_order_book_imbalance": Decimal("-0.60"),
        "min_expected_edge_buffer_pct": Decimal("0.0003"),
        "min_stop_distance_ratio": Decimal("0.0005"),
        "stop_loss_atr_multiple": Decimal("1.4"),
        "take_profit_atr_multiple": Decimal("2.0"),
    },
}

BLOCKER_LABELS: dict[str, str] = {
    "low_volatility": "Low volatility",
    "weak_signal": "Weak signal",
    "spread_too_wide": "Spread too wide",
    "edge_below_fees": "Edge below fees",
    "insufficient_candles": "Insufficient candles",
    "no_trend_confirmation": "No trend confirmation",
}

REASON_TO_BLOCKER: dict[str, str] = {
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


@dataclass(slots=True)
class ThresholdChange:
    """One suggested threshold change."""

    threshold: str
    current_value: Decimal
    suggested_value: Decimal


@dataclass(slots=True)
class ProfileCalibrationRecommendation:
    """Calibration recommendation for one paper-trading profile."""

    profile: str
    profile_health: str
    recommendation: str
    reason: str
    affected_thresholds: list[ThresholdChange]
    expected_impact: str
    sample_size_warning: str | None
    trade_count: int
    win_rate: Decimal | None
    expectancy: Decimal | None
    fees_paid: Decimal
    blocker_share: dict[str, Decimal]


@dataclass(slots=True)
class ProfileCalibrationReport:
    """Complete profile calibration response."""

    symbol: str | None
    start_date: date | None
    end_date: date | None
    recommendations: list[ProfileCalibrationRecommendation]
    active_tuning: "ProfileTuningPreview | None" = None
    pending_tuning: "ProfileTuningPreview | None" = None


@dataclass(slots=True)
class ProfileTuningPreview:
    """Persisted tuning-set preview for operator review."""

    version_id: str
    profile: str
    status: str
    created_at: date
    applied_at: date | None
    baseline_version_id: str | None
    reason: str
    affected_thresholds: list[ThresholdChange]


@dataclass(slots=True)
class ProfileCalibrationComparisonMetrics:
    """Before/after performance metrics for one tuning scope."""

    session_count: int
    trade_count: int
    expectancy: Decimal | None
    profit_factor: Decimal | None
    win_rate: Decimal | None
    max_drawdown: Decimal | None
    fees_paid: Decimal
    blocker_distribution: dict[str, Decimal]


@dataclass(slots=True)
class ProfileCalibrationComparison:
    """Before/after comparison for one applied profile tuning."""

    symbol: str
    profile: str
    start_date: date | None
    end_date: date | None
    comparison_status: str
    status_message: str | None
    active_tuning: ProfileTuningPreview | None
    baseline_tuning: ProfileTuningPreview | None
    before: ProfileCalibrationComparisonMetrics | None
    after: ProfileCalibrationComparisonMetrics | None


def _to_optional_rate(numerator: int, denominator: int) -> Decimal | None:
    """Return a percentage rate rounded for display."""

    if denominator <= 0:
        return None
    return (
        (Decimal(numerator) / Decimal(denominator)) * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_optional_expectancy(pnl: Decimal, count: int) -> Decimal | None:
    """Return expectancy per trade when sample size is non-zero."""

    if count <= 0:
        return None
    return (pnl / Decimal(count)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _parse_payload(event: RunnerEventRecord) -> dict[str, object]:
    """Parse a persisted runner event payload."""

    try:
        payload = json.loads(event.payload_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _profile_blockers(events: list[RunnerEventRecord], profile: str) -> Counter[str]:
    """Return blocker counts for one profile."""

    counts: Counter[str] = Counter()
    for event in events:
        payload = _parse_payload(event)
        event_profile = str(payload.get("trading_profile", ""))
        if event_profile != profile:
            continue
        raw_codes = payload.get("reason_codes", [])
        if isinstance(raw_codes, str):
            raw_codes = [raw_codes]
        if not isinstance(raw_codes, list):
            continue
        for code in raw_codes:
            blocker_key = REASON_TO_BLOCKER.get(str(code))
            if blocker_key is not None:
                counts[blocker_key] += 1
    return counts


def _profile_metrics(trades: list[TradeRecord], profile: str) -> tuple[list[TradeRecord], list[TradeRecord]]:
    """Return executed trades and closed trades for one profile."""

    profile_trades = [
        trade
        for trade in trades
        if trade.status == "executed" and trade.trading_profile == profile
    ]
    closed_trades = [trade for trade in profile_trades if trade.side == "SELL"]
    return profile_trades, closed_trades


def _profile_fees_paid(fills: list[FillRecord], profile: str) -> Decimal:
    """Return total paid fees for one profile scope."""

    return sum(
        (fill.fee_paid for fill in fills if fill.trading_profile == profile),
        start=Decimal("0"),
    )


def _blocker_share(counter: Counter[str]) -> dict[str, Decimal]:
    """Return blocker share percentages."""

    total = sum(counter.values())
    if total <= 0:
        return {}
    return {
        key: ((Decimal(value) / Decimal(total)) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for key, value in counter.items()
    }


def _shift(current: Decimal, delta: Decimal) -> Decimal:
    """Return a stable suggested threshold adjustment."""

    return (current + delta).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _too_strict_recommendation(profile: str, blockers: Counter[str]) -> tuple[str, list[ThresholdChange], str]:
    """Return a loosening recommendation for an over-constrained profile."""

    thresholds = PROFILE_THRESHOLDS[profile]
    affected = [
        ThresholdChange(
            threshold="min_atr_ratio",
            current_value=thresholds["min_atr_ratio"],
            suggested_value=_shift(thresholds["min_atr_ratio"], Decimal("-0.0001")),
        ),
        ThresholdChange(
            threshold="min_expected_edge_buffer_pct",
            current_value=thresholds["min_expected_edge_buffer_pct"],
            suggested_value=_shift(thresholds["min_expected_edge_buffer_pct"], Decimal("-0.0002")),
        ),
    ]
    if blockers.get("no_trend_confirmation", 0) > blockers.get("low_volatility", 0):
        affected.append(
            ThresholdChange(
                threshold="min_order_book_imbalance",
                current_value=thresholds["min_order_book_imbalance"],
                suggested_value=_shift(thresholds["min_order_book_imbalance"], Decimal("-0.05")),
            )
        )
    reason = "Observed blocker pressure shows this profile is waiting too often for confirmation or usable volatility."
    impact = "Loosening these thresholds should allow more paper entries without removing cost-aware risk checks."
    return reason, affected, impact


def _too_loose_recommendation(profile: str, blockers: Counter[str]) -> tuple[str, list[ThresholdChange], str]:
    """Return a tightening recommendation for an over-active profile."""

    thresholds = PROFILE_THRESHOLDS[profile]
    affected = [
        ThresholdChange(
            threshold="min_expected_edge_buffer_pct",
            current_value=thresholds["min_expected_edge_buffer_pct"],
            suggested_value=_shift(thresholds["min_expected_edge_buffer_pct"], Decimal("0.0003")),
        ),
        ThresholdChange(
            threshold="min_atr_ratio",
            current_value=thresholds["min_atr_ratio"],
            suggested_value=_shift(thresholds["min_atr_ratio"], Decimal("0.0001")),
        ),
        ThresholdChange(
            threshold="max_spread_ratio",
            current_value=thresholds["max_spread_ratio"],
            suggested_value=max(
                Decimal("0.0005"),
                _shift(thresholds["max_spread_ratio"], Decimal("-0.0005")),
            ),
        ),
    ]
    if blockers.get("edge_below_fees", 0) > 0:
        affected.append(
            ThresholdChange(
                threshold="take_profit_atr_multiple",
                current_value=thresholds["take_profit_atr_multiple"],
                suggested_value=_shift(thresholds["take_profit_atr_multiple"], Decimal("0.4")),
            )
        )
    reason = "This profile is taking enough trades, but realized expectancy and blocker mix suggest the entries are too loose."
    impact = "Tightening should reduce low-edge paper trades and improve realized trade quality."
    return reason, affected, impact


def _drawdown_warning(drawdown: DrawdownSummary) -> bool:
    """Return whether drawdown pressure is materially elevated."""

    return drawdown.current_drawdown_pct >= Decimal("0.05") or drawdown.max_drawdown_pct >= Decimal("0.08")


def _preview_from_tuning_set(record: ProfileTuningSetRecord | None) -> ProfileTuningPreview | None:
    """Convert a stored tuning set into a preview payload."""

    if record is None:
        return None
    baseline = PROFILE_THRESHOLDS[record.profile].copy()
    try:
        current_config = json.loads(record.config_json)
    except json.JSONDecodeError:
        current_config = {}
    affected_thresholds: list[ThresholdChange] = []
    if isinstance(current_config, dict):
        for threshold, current_value in baseline.items():
            if threshold not in current_config:
                continue
            suggested_value = Decimal(str(current_config[threshold]))
            if suggested_value == current_value:
                continue
            affected_thresholds.append(
                ThresholdChange(
                    threshold=threshold,
                    current_value=current_value,
                    suggested_value=suggested_value,
                )
            )
    return ProfileTuningPreview(
        version_id=record.version_id,
        profile=record.profile,
        status=record.status,
        created_at=record.created_at.date(),
        applied_at=record.applied_at.date() if record.applied_at is not None else None,
        baseline_version_id=record.baseline_version_id,
        reason=record.reason,
        affected_thresholds=affected_thresholds,
    )


def with_tuning_previews(
    report: ProfileCalibrationReport,
    *,
    active_tuning: ProfileTuningSetRecord | None,
    pending_tuning: ProfileTuningSetRecord | None,
) -> ProfileCalibrationReport:
    """Attach persisted tuning previews to a calibration report."""

    report.active_tuning = _preview_from_tuning_set(active_tuning)
    report.pending_tuning = _preview_from_tuning_set(pending_tuning)
    return report


def _event_session_id(event: RunnerEventRecord) -> str | None:
    """Return the persisted session id embedded in an event payload."""

    payload = _parse_payload(event)
    session_id = payload.get("session_id")
    return str(session_id) if isinstance(session_id, str) and session_id else None


def _calculate_profit_factor(closed_trades: list[TradeRecord]) -> Decimal | None:
    """Return profit factor for closed trades."""

    gross_profit = sum(
        (trade.realized_pnl for trade in closed_trades if trade.realized_pnl > Decimal("0")),
        start=Decimal("0"),
    )
    gross_loss = sum(
        (trade.realized_pnl for trade in closed_trades if trade.realized_pnl < Decimal("0")),
        start=Decimal("0"),
    )
    if gross_loss == Decimal("0"):
        return None
    return (gross_profit / abs(gross_loss)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _calculate_realized_drawdown(closed_trades: list[TradeRecord]) -> Decimal | None:
    """Return realized PnL drawdown over the closed-trade path."""

    if not closed_trades:
        return None
    running_total = Decimal("0")
    running_peak = Decimal("0")
    max_drawdown = Decimal("0")
    for trade in sorted(closed_trades, key=lambda item: item.event_time):
        running_total += trade.realized_pnl
        running_peak = max(running_peak, running_total)
        max_drawdown = max(max_drawdown, running_peak - running_total)
    return max_drawdown.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _comparison_metrics(
    *,
    session_ids: set[str],
    trades: list[TradeRecord],
    fills: list[FillRecord],
    events: list[RunnerEventRecord],
) -> ProfileCalibrationComparisonMetrics | None:
    """Build comparison metrics for one group of session ids."""

    if not session_ids:
        return None
    scoped_trades = [
        trade
        for trade in trades
        if trade.session_id is not None and trade.session_id in session_ids and trade.status == "executed"
    ]
    closed_trades = [trade for trade in scoped_trades if trade.side == "SELL"]
    scoped_fills = [
        fill for fill in fills if fill.session_id is not None and fill.session_id in session_ids
    ]
    scoped_events = [
        event for event in events if _event_session_id(event) in session_ids
    ]
    blocker_share = _blocker_share(
        Counter(
            blocker
            for event in scoped_events
            for code in _parse_payload(event).get("reason_codes", [])
            for blocker in [REASON_TO_BLOCKER.get(str(code))]
            if blocker is not None
        )
    )
    realized_pnl = sum((trade.realized_pnl for trade in closed_trades), start=Decimal("0"))
    trade_count = len(closed_trades)
    return ProfileCalibrationComparisonMetrics(
        session_count=len(session_ids),
        trade_count=trade_count,
        expectancy=_to_optional_expectancy(realized_pnl, trade_count),
        profit_factor=_calculate_profit_factor(closed_trades),
        win_rate=_to_optional_rate(
            sum(1 for trade in closed_trades if trade.realized_pnl > Decimal("0")),
            trade_count,
        ),
        max_drawdown=_calculate_realized_drawdown(closed_trades),
        fees_paid=sum((fill.fee_paid for fill in scoped_fills), start=Decimal("0")),
        blocker_distribution=blocker_share,
    )


def build_profile_calibration_report(
    *,
    trades: list[TradeRecord],
    fills: list[FillRecord],
    events: list[RunnerEventRecord],
    drawdown: DrawdownSummary,
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ProfileCalibrationReport:
    """Build profile calibration recommendations from paper-trade outcomes."""

    recommendations: list[ProfileCalibrationRecommendation] = []
    for profile in PROFILE_ORDER:
        profile_trades, closed_trades = _profile_metrics(trades, profile)
        blockers = _profile_blockers(events, profile)
        blocker_share = _blocker_share(blockers)
        trade_count = len(closed_trades)
        realized_pnl = sum((trade.realized_pnl for trade in closed_trades), start=Decimal("0"))
        fees_paid = _profile_fees_paid(fills, profile)
        expectancy = _to_optional_expectancy(realized_pnl, trade_count)
        win_rate = _to_optional_rate(
            sum(1 for trade in closed_trades if trade.realized_pnl > Decimal("0")),
            trade_count,
        )
        trades_per_hour = None
        if profile_trades:
            first_time = min(trade.event_time for trade in profile_trades)
            last_time = max(trade.event_time for trade in profile_trades)
            active_seconds = max((last_time - first_time).total_seconds(), 1)
            trades_per_hour = (
                Decimal(len(profile_trades)) * Decimal("3600") / Decimal(active_seconds)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        sample_size_warning: str | None = None
        recommendation = "keep"
        profile_health = "healthy"
        reason = "Observed paper outcomes do not yet justify a threshold change."
        expected_impact = "Keep collecting paper trades before retuning this profile."
        affected_thresholds: list[ThresholdChange] = []

        if trade_count < 2 and sum(blockers.values()) < 4:
            profile_health = "insufficient_data"
            sample_size_warning = "Sample size is still too small for trustworthy profile tuning."
        else:
            high_blocker_share = max(blocker_share.values(), default=Decimal("0"))
            too_strict = (
                trade_count < 2
                and high_blocker_share >= Decimal("50.00")
                and (
                    blockers.get("low_volatility", 0)
                    + blockers.get("insufficient_candles", 0)
                    + blockers.get("no_trend_confirmation", 0)
                ) >= max(2, sum(blockers.values()) // 2)
            )
            too_loose = (
                trade_count >= 2
                and expectancy is not None
                and expectancy <= Decimal("0")
                and (
                    (trades_per_hour is not None and trades_per_hour >= Decimal("1.00"))
                    or blockers.get("edge_below_fees", 0) >= 1
                    or _drawdown_warning(drawdown)
                )
            )

            fee_drag = (
                (
                    blockers.get("edge_below_fees", 0) >= 2
                    or (
                        fees_paid > Decimal("0")
                        and abs(realized_pnl) <= fees_paid
                    )
                )
                and expectancy is not None
                and expectancy <= Decimal("0")
            )

            if too_strict:
                profile_health = "too_strict"
                recommendation = "loosen"
                reason, affected_thresholds, expected_impact = _too_strict_recommendation(profile, blockers)
            elif fee_drag:
                profile_health = "fee_drag"
                recommendation = "tighten"
                reason = "Paper costs are consuming too much of the observed edge for this profile."
                affected_thresholds = [
                    ThresholdChange(
                        threshold="min_expected_edge_buffer_pct",
                        current_value=PROFILE_THRESHOLDS[profile]["min_expected_edge_buffer_pct"],
                        suggested_value=_shift(PROFILE_THRESHOLDS[profile]["min_expected_edge_buffer_pct"], Decimal("0.0004")),
                    ),
                    ThresholdChange(
                        threshold="take_profit_atr_multiple",
                        current_value=PROFILE_THRESHOLDS[profile]["take_profit_atr_multiple"],
                        suggested_value=_shift(PROFILE_THRESHOLDS[profile]["take_profit_atr_multiple"], Decimal("0.4")),
                    ),
                ]
                expected_impact = "This should filter more low-edge entries before fees and slippage erase the move."
            elif too_loose:
                profile_health = "too_loose"
                recommendation = "tighten"
                reason, affected_thresholds, expected_impact = _too_loose_recommendation(profile, blockers)

        recommendations.append(
            ProfileCalibrationRecommendation(
                profile=profile,
                profile_health=profile_health,
                recommendation=recommendation,
                reason=reason,
                affected_thresholds=affected_thresholds,
                expected_impact=expected_impact,
                sample_size_warning=sample_size_warning,
                trade_count=trade_count,
                win_rate=win_rate,
                expectancy=expectancy,
                fees_paid=fees_paid,
                blocker_share=blocker_share,
            )
        )

    return ProfileCalibrationReport(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        recommendations=recommendations,
    )


def build_profile_calibration_comparison(
    *,
    symbol: str,
    profile: str,
    start_date: date | None,
    end_date: date | None,
    session_runs: list[PaperSessionRunRecord],
    trades: list[TradeRecord],
    fills: list[FillRecord],
    events: list[RunnerEventRecord],
    active_tuning: ProfileTuningSetRecord | None,
    baseline_tuning: ProfileTuningSetRecord | None = None,
    session_id: str | None = None,
) -> ProfileCalibrationComparison:
    """Build a before/after comparison for the latest applied tuning set."""

    normalized_profile = profile.lower()
    filtered_runs = [
        run
        for run in session_runs
        if run.symbol == symbol and run.trading_profile == normalized_profile
    ]
    if start_date is not None:
        filtered_runs = [run for run in filtered_runs if run.started_at.date() >= start_date]
    if end_date is not None:
        filtered_runs = [run for run in filtered_runs if run.started_at.date() <= end_date]

    if active_tuning is None:
        return ProfileCalibrationComparison(
            symbol=symbol,
            profile=normalized_profile,
            start_date=start_date,
            end_date=end_date,
            comparison_status="insufficient_data",
            status_message="No applied tuning set exists yet for this profile.",
            active_tuning=None,
            baseline_tuning=None,
            before=None,
            after=None,
        )

    after_runs = [
        run for run in filtered_runs if run.tuning_version_id == active_tuning.version_id
    ]
    if session_id is not None:
        after_runs = [run for run in after_runs if run.session_id == session_id]

    before_runs = (
        [
            run
            for run in filtered_runs
            if run.tuning_version_id == active_tuning.baseline_version_id
        ]
        if active_tuning.baseline_version_id is not None
        else [run for run in filtered_runs if run.tuning_version_id is None]
    )

    before_metrics = _comparison_metrics(
        session_ids={run.session_id for run in before_runs},
        trades=trades,
        fills=fills,
        events=events,
    )
    after_metrics = _comparison_metrics(
        session_ids={run.session_id for run in after_runs},
        trades=trades,
        fills=fills,
        events=events,
    )
    if before_metrics is None or after_metrics is None:
        return ProfileCalibrationComparison(
            symbol=symbol,
            profile=normalized_profile,
            start_date=start_date,
            end_date=end_date,
            comparison_status="insufficient_data",
            status_message="Need both baseline and tuned paper sessions before comparison is meaningful.",
            active_tuning=_preview_from_tuning_set(active_tuning),
            baseline_tuning=_preview_from_tuning_set(baseline_tuning),
            before=before_metrics,
            after=after_metrics,
        )

    return ProfileCalibrationComparison(
        symbol=symbol,
        profile=normalized_profile,
        start_date=start_date,
        end_date=end_date,
        comparison_status="ready",
        status_message=None,
        active_tuning=_preview_from_tuning_set(active_tuning),
        baseline_tuning=_preview_from_tuning_set(baseline_tuning),
        before=before_metrics,
        after=after_metrics,
    )
