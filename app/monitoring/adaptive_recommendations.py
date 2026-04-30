"""Evidence-based adaptive recommendation analytics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Literal

from app.monitoring.signal_validation import SignalOutcome, evaluate_signal_outcomes
from app.storage.models import HistoricalCandleRecord, SignalValidationSnapshotRecord


RecommendationType = Literal[
    "raise_min_confidence",
    "lower_min_confidence",
    "avoid_regime",
    "prefer_horizon",
    "avoid_horizon",
    "restrict_symbol",
    "watch_symbol",
    "restrict_action_type",
    "tighten_risk_grade",
    "loosen_risk_grade",
    "require_confirmation",
    "keep_current_settings",
    "insufficient_data",
]
AffectedScope = Literal[
    "global",
    "symbol",
    "regime",
    "horizon",
    "action_type",
    "risk_grade",
    "confidence_bucket",
]
EvidenceStrength = Literal["insufficient", "weak", "mixed", "promising", "strong"]

MINIMUM_SAMPLE_REQUIRED = 6
MINIMUM_GROUP_SAMPLE_REQUIRED = 3


@dataclass(slots=True)
class AdaptiveRecommendation:
    """One deterministic adaptive setting recommendation."""

    recommendation_id: str
    recommendation_type: RecommendationType
    affected_scope: AffectedScope
    affected_value: str
    current_observation: str
    suggested_change: str
    evidence_summary: str
    expected_benefit: str
    evidence_strength: EvidenceStrength
    sample_size: int
    minimum_sample_required: int
    warnings: list[str] = field(default_factory=list)
    do_not_auto_apply: bool = True


@dataclass(slots=True)
class AdaptiveRecommendationReport:
    """Complete adaptive recommendation response."""

    symbol: str | None
    start_date: date | None
    end_date: date | None
    status: Literal["ready", "insufficient_data"]
    status_message: str | None
    recommendations: list[AdaptiveRecommendation]


@dataclass(slots=True)
class _OutcomeView:
    outcome: SignalOutcome
    snapshot: SignalValidationSnapshotRecord


@dataclass(slots=True)
class _GroupMetric:
    name: str
    sample_size: int
    win_rate_pct: Decimal | None
    expectancy_pct: Decimal | None
    false_positive_rate_pct: Decimal | None
    blocked_sample_size: int = 0


def build_adaptive_recommendation_report(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
    symbol: str | None,
    start_date: date | None,
    end_date: date | None,
    horizon: str | None = None,
    action: str | None = None,
    regime: str | None = None,
    risk_grade: str | None = None,
) -> AdaptiveRecommendationReport:
    """Build conservative, evidence-based adaptive recommendations."""

    filtered_snapshots = _filter_snapshots(
        snapshots=snapshots,
        action=action,
        regime=regime,
        risk_grade=risk_grade,
    )
    outcomes = evaluate_signal_outcomes(
        snapshots=filtered_snapshots,
        candles_by_symbol=candles_by_symbol,
    )
    if horizon is not None:
        outcomes = [item for item in outcomes if item.horizon == horizon]
    views = _views(outcomes=outcomes, snapshots=filtered_snapshots)
    directional = [item for item in views if item.outcome.directional_return_pct is not None]

    if len(directional) < MINIMUM_SAMPLE_REQUIRED:
        return AdaptiveRecommendationReport(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            status="insufficient_data",
            status_message=(
                f"Need at least {MINIMUM_SAMPLE_REQUIRED} evaluated directional outcomes "
                "before recommending adaptive threshold changes."
            ),
            recommendations=[
                AdaptiveRecommendation(
                    recommendation_id="insufficient_data:global:all",
                    recommendation_type="insufficient_data",
                    affected_scope="global",
                    affected_value="all",
                    current_observation=f"Only {len(directional)} evaluated directional outcomes are available.",
                    suggested_change="Collect more paper-mode signal outcomes before changing thresholds.",
                    evidence_summary="Sample size is too small for evidence-based adaptation.",
                    expected_benefit="Avoids overfitting settings to weak or noisy evidence.",
                    evidence_strength="insufficient",
                    sample_size=len(directional),
                    minimum_sample_required=MINIMUM_SAMPLE_REQUIRED,
                    warnings=["No adaptive recommendation should be applied from this sample."],
                )
            ],
        )

    recommendations: list[AdaptiveRecommendation] = []
    recommendations.extend(_confidence_recommendations(directional))
    recommendations.extend(_regime_recommendations(directional))
    recommendations.extend(_horizon_recommendations(directional))
    recommendations.extend(_symbol_recommendations(directional))
    recommendations.extend(_action_recommendations(directional))
    recommendations.extend(_risk_recommendations(directional))
    recommendations.extend(_blocker_recommendations(directional))

    if not recommendations:
        recommendations.append(
            AdaptiveRecommendation(
                recommendation_id="keep_current_settings:global:all",
                recommendation_type="keep_current_settings",
                affected_scope="global",
                affected_value="all",
                current_observation="No measured group shows a clear threshold or rule change opportunity.",
                suggested_change="Keep current paper settings and continue collecting validation outcomes.",
                evidence_summary=f"{len(directional)} evaluated directional outcomes did not justify a conservative change.",
                expected_benefit="Avoids unnecessary changes while evidence remains mixed or balanced.",
                evidence_strength="mixed",
                sample_size=len(directional),
                minimum_sample_required=MINIMUM_SAMPLE_REQUIRED,
            )
        )

    return AdaptiveRecommendationReport(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        status="ready",
        status_message=None,
        recommendations=recommendations,
    )


def _filter_snapshots(
    *,
    snapshots: list[SignalValidationSnapshotRecord],
    action: str | None,
    regime: str | None,
    risk_grade: str | None,
) -> list[SignalValidationSnapshotRecord]:
    filtered = snapshots
    if action is not None:
        filtered = [item for item in filtered if item.final_action == action]
    if regime is not None:
        filtered = [item for item in filtered if item.regime_label == regime]
    if risk_grade is not None:
        filtered = [item for item in filtered if item.risk_grade == risk_grade]
    return filtered


def _views(
    *,
    outcomes: list[SignalOutcome],
    snapshots: list[SignalValidationSnapshotRecord],
) -> list[_OutcomeView]:
    by_id = {snapshot.id: snapshot for snapshot in snapshots if snapshot.id is not None}
    by_key = {
        (snapshot.symbol, snapshot.timestamp, snapshot.final_action): snapshot
        for snapshot in snapshots
    }
    views: list[_OutcomeView] = []
    for outcome in outcomes:
        snapshot = by_id.get(outcome.signal_id)
        if snapshot is None:
            snapshot = by_key.get((outcome.symbol, outcome.timestamp, outcome.action))
        if snapshot is not None:
            views.append(_OutcomeView(outcome=outcome, snapshot=snapshot))
    return views


def _confidence_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    recommendations: list[AdaptiveRecommendation] = []
    metrics = _group_metrics(views, lambda item: item.outcome.confidence_bucket)
    for metric in metrics:
        if metric.name in {"low", "medium"} and _negative(metric):
            threshold = "70%" if metric.name == "low" else "75%"
            recommendations.append(
                _recommendation(
                    recommendation_type="raise_min_confidence",
                    affected_scope="confidence_bucket",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Raise minimum confidence above the {metric.name} bucket; start testing at {threshold}.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Filters out confidence ranges with measured negative expectancy.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Do not apply automatically; confirm with the next paper session.",
                )
            )
    blocked = _build_group_metric(
        "blocked_or_ignored",
        [item for item in views if item.outcome.ignored_or_blocked],
    )
    if _strong_positive(blocked):
        recommendations.append(
            _recommendation(
                recommendation_type="lower_min_confidence",
                affected_scope="global",
                affected_value="minimum_confidence",
                current_observation=_metric_observation(blocked),
                suggested_change="Review whether some blocked lower-confidence setups deserve a narrower paper test.",
                evidence_summary=_metric_summary(blocked),
                expected_benefit="May recover missed edge only if blocked setups continue to perform strongly.",
                evidence_strength="strong",
                metric=blocked,
                warning="Loosening requires manual review because it increases trade frequency risk.",
            )
        )
    return recommendations


def _regime_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    recommendations: list[AdaptiveRecommendation] = []
    metrics = _group_metrics(views, lambda item: item.snapshot.regime_label or "unknown")
    for metric in metrics:
        if metric.name == "unknown":
            continue
        if _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="avoid_regime",
                    affected_scope="regime",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Avoid paper entries during {metric.name} until expectancy improves.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Reduces exposure to regimes with measured losing outcomes.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Regime avoidance should remain paper-only until revalidated.",
                )
            )
        if metric.name in {"choppy", "high_volatility"} and _confirmation_needed(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="require_confirmation",
                    affected_scope="regime",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Require extra candle or breakout confirmation in {metric.name}.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Reduces false positives in unstable conditions.",
                    evidence_strength="mixed",
                    metric=metric,
                    warning="Confirmation rules should be evaluated before manual application.",
                )
            )
    return recommendations


def _horizon_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    metrics = _group_metrics(views, lambda item: item.outcome.horizon)
    recommendations: list[AdaptiveRecommendation] = []
    for metric in metrics:
        if _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="avoid_horizon",
                    affected_scope="horizon",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Do not prioritize {metric.name} signals while expectancy is negative.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Avoids acting on horizons with measured poor follow-through.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Keep collecting outcomes before removing the horizon entirely.",
                )
            )
    best = _best_positive_horizon(metrics)
    if best is not None:
        recommendations.append(
            _recommendation(
                recommendation_type="prefer_horizon",
                affected_scope="horizon",
                affected_value=best.name,
                current_observation=_metric_observation(best),
                suggested_change=f"Prefer {best.name} when current setup evidence is otherwise acceptable.",
                evidence_summary=_metric_summary(best),
                expected_benefit="Focuses paper consideration on the horizon with the clearest measured edge.",
                evidence_strength=_strength(best),
                metric=best,
                warning="Preference is advisory and should not force trades by itself.",
            )
        )
    return recommendations


def _symbol_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    recommendations: list[AdaptiveRecommendation] = []
    for metric in _group_metrics(views, lambda item: item.outcome.symbol):
        if _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="restrict_symbol",
                    affected_scope="symbol",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Restrict {metric.name} to watch-only until signal expectancy improves.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Avoids symbols currently producing losing signal outcomes.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Symbol restrictions should be reviewed after more samples.",
                )
            )
        elif _watch_only_symbol(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="watch_symbol",
                    affected_scope="symbol",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Keep {metric.name} on watch until the edge is clearer.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Prevents premature symbol disablement when evidence is mixed.",
                    evidence_strength="mixed",
                    metric=metric,
                    warning="No restriction is justified yet.",
                )
            )
    return recommendations


def _action_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    recommendations: list[AdaptiveRecommendation] = []
    for metric in _group_metrics(views, lambda item: item.outcome.action):
        if metric.name in {"buy", "sell_exit"} and _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="restrict_action_type",
                    affected_scope="action_type",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Restrict {metric.name} signals until measured outcomes recover.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Reduces action types that are currently losing after costs.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Restriction is advisory and must not auto-disable execution.",
                )
            )
    return recommendations


def _risk_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    recommendations: list[AdaptiveRecommendation] = []
    for metric in _group_metrics(views, lambda item: item.outcome.risk_grade):
        if metric.name in {"medium", "high"} and _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="tighten_risk_grade",
                    affected_scope="risk_grade",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Tighten or avoid {metric.name} risk-grade setups in paper automation consideration.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Reduces exposure to risk grades with measured losing outcomes.",
                    evidence_strength="weak",
                    metric=metric,
                    warning="Risk grade changes require manual review.",
                )
            )
        elif metric.name == "low" and _strong_positive(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="loosen_risk_grade",
                    affected_scope="risk_grade",
                    affected_value=metric.name,
                    current_observation=_metric_observation(metric),
                    suggested_change="Consider allowing low-risk-grade setups with slightly fewer confirmations in paper mode.",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="May reduce missed low-risk opportunities while preserving safety.",
                    evidence_strength="strong",
                    metric=metric,
                    warning="Loosening must be manually queued and compared against baseline.",
                )
            )
    return recommendations


def _blocker_recommendations(views: list[_OutcomeView]) -> list[AdaptiveRecommendation]:
    groups: dict[str, list[_OutcomeView]] = defaultdict(list)
    for item in views:
        for blocker in item.outcome.blocker_reasons:
            groups[blocker].append(item)
    recommendations: list[AdaptiveRecommendation] = []
    for blocker, group in groups.items():
        metric = _build_group_metric(blocker, group)
        if _negative(metric):
            recommendations.append(
                _recommendation(
                    recommendation_type="keep_current_settings",
                    affected_scope="global",
                    affected_value=blocker,
                    current_observation=_metric_observation(metric),
                    suggested_change=f"Keep blocker active: {blocker}",
                    evidence_summary=_metric_summary(metric),
                    expected_benefit="Preserves blockers that appear to protect against losing signals.",
                    evidence_strength="promising",
                    metric=metric,
                    warning="This is not a loosening recommendation.",
                )
            )
    return recommendations


def _group_metrics(
    views: list[_OutcomeView],
    key_selector: Callable[[_OutcomeView], str],
) -> list[_GroupMetric]:
    groups: dict[str, list[_OutcomeView]] = defaultdict(list)
    for item in views:
        groups[str(key_selector(item))].append(item)
    return [
        metric
        for metric in (_build_group_metric(name, group) for name, group in groups.items())
        if metric.sample_size >= MINIMUM_GROUP_SAMPLE_REQUIRED
    ]


def _build_group_metric(name: str, views: list[_OutcomeView]) -> _GroupMetric:
    wins = [item for item in views if item.outcome.survived_fees_slippage]
    losses = [item for item in views if not item.outcome.survived_fees_slippage]
    returns = [
        item.outcome.directional_return_pct
        for item in views
        if item.outcome.directional_return_pct is not None
    ]
    return _GroupMetric(
        name=name,
        sample_size=len(views),
        win_rate_pct=_rate(len(wins), len(views)),
        expectancy_pct=_avg(returns),
        false_positive_rate_pct=_rate(len(losses), len(views)),
        blocked_sample_size=sum(1 for item in views if item.outcome.ignored_or_blocked),
    )


def _best_positive_horizon(metrics: list[_GroupMetric]) -> _GroupMetric | None:
    positive = [metric for metric in metrics if _positive(metric)]
    if not positive:
        return None
    ranked = sorted(
        positive,
        key=lambda item: (item.expectancy_pct or Decimal("0"), item.win_rate_pct or Decimal("0")),
        reverse=True,
    )
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    if runner_up is None:
        return best
    edge_gap = (best.expectancy_pct or Decimal("0")) - (runner_up.expectancy_pct or Decimal("0"))
    return best if edge_gap >= Decimal("0.5000") else None


def _recommendation(
    *,
    recommendation_type: RecommendationType,
    affected_scope: AffectedScope,
    affected_value: str,
    current_observation: str,
    suggested_change: str,
    evidence_summary: str,
    expected_benefit: str,
    evidence_strength: EvidenceStrength,
    metric: _GroupMetric,
    warning: str,
) -> AdaptiveRecommendation:
    return AdaptiveRecommendation(
        recommendation_id=f"{recommendation_type}:{affected_scope}:{_slug(affected_value)}",
        recommendation_type=recommendation_type,
        affected_scope=affected_scope,
        affected_value=affected_value,
        current_observation=current_observation,
        suggested_change=suggested_change,
        evidence_summary=evidence_summary,
        expected_benefit=expected_benefit,
        evidence_strength=evidence_strength,
        sample_size=metric.sample_size,
        minimum_sample_required=MINIMUM_GROUP_SAMPLE_REQUIRED,
        warnings=[warning],
    )


def _negative(metric: _GroupMetric) -> bool:
    expectancy = metric.expectancy_pct
    false_positive = metric.false_positive_rate_pct or Decimal("0")
    return (
        expectancy is not None
        and metric.sample_size >= MINIMUM_GROUP_SAMPLE_REQUIRED
        and (expectancy < Decimal("0") or false_positive >= Decimal("60"))
    )


def _positive(metric: _GroupMetric) -> bool:
    return (
        metric.expectancy_pct is not None
        and metric.win_rate_pct is not None
        and metric.expectancy_pct > Decimal("0.5000")
        and metric.win_rate_pct >= Decimal("55")
    )


def _strong_positive(metric: _GroupMetric) -> bool:
    return (
        metric.sample_size >= MINIMUM_SAMPLE_REQUIRED
        and metric.expectancy_pct is not None
        and metric.win_rate_pct is not None
        and metric.expectancy_pct > Decimal("0.7500")
        and metric.win_rate_pct >= Decimal("65")
    )


def _mixed(metric: _GroupMetric) -> bool:
    if metric.expectancy_pct is None or metric.win_rate_pct is None:
        return False
    return Decimal("-0.2500") <= metric.expectancy_pct <= Decimal("0.5000")


def _watch_only_symbol(metric: _GroupMetric) -> bool:
    if metric.expectancy_pct is None:
        return False
    false_positive = metric.false_positive_rate_pct or Decimal("0")
    return Decimal("0") <= metric.expectancy_pct <= Decimal("0.2500") and false_positive >= Decimal("45")


def _confirmation_needed(metric: _GroupMetric) -> bool:
    false_positive = metric.false_positive_rate_pct or Decimal("0")
    expectancy = metric.expectancy_pct or Decimal("0")
    return false_positive >= Decimal("45") or expectancy <= Decimal("0.2500")


def _strength(metric: _GroupMetric) -> EvidenceStrength:
    if _strong_positive(metric):
        return "strong"
    if _positive(metric):
        return "promising"
    if _negative(metric):
        return "weak"
    return "mixed"


def _metric_observation(metric: _GroupMetric) -> str:
    return (
        f"{metric.name} has {metric.sample_size} evaluated samples, "
        f"{_fmt(metric.win_rate_pct)} win rate, {_fmt(metric.expectancy_pct)} expectancy, "
        f"and {_fmt(metric.false_positive_rate_pct)} false-positive rate."
    )


def _metric_summary(metric: _GroupMetric) -> str:
    return (
        f"Measured from {metric.sample_size} forward signal outcomes after fees/slippage; "
        f"expectancy={_fmt(metric.expectancy_pct)}, win_rate={_fmt(metric.win_rate_pct)}."
    )


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


def _fmt(value: Decimal | None) -> str:
    return "unknown" if value is None else f"{value}%"


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value.lower()).strip("_")
