"""Historical similar-setup outcome analytics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.monitoring.signal_validation import (
    VALIDATION_HORIZONS,
    SignalOutcome,
    evaluate_signal_outcomes,
)
from app.storage.models import HistoricalCandleRecord, SignalValidationSnapshotRecord


MIN_SIMILAR_DIRECTIONAL_SAMPLES = 3


@dataclass(slots=True)
class SimilarSetupDescriptor:
    """Comparable setup attributes used for historical matching."""

    symbol: str | None
    action: str | None
    confidence_bucket: str | None
    risk_grade: str | None
    regime_label: str | None
    preferred_horizon: str | None
    technical_direction: str | None
    sentiment_direction: str | None
    pattern_behavior: str | None
    blocker_state: str | None


@dataclass(slots=True)
class SimilarSetupHorizonMetric:
    """Outcome metrics for matching setups on one horizon."""

    horizon: str
    sample_size: int
    win_rate_pct: Decimal | None
    expectancy_pct: Decimal | None
    average_favorable_move_pct: Decimal | None
    average_adverse_move_pct: Decimal | None


@dataclass(slots=True)
class SimilarSetupReport:
    """Historical outcome report for setups similar to the current signal."""

    status: Literal["ready", "insufficient_data"]
    reliability_label: Literal["insufficient_data", "weak", "mixed", "promising", "strong"]
    matching_sample_size: int
    best_horizon: str | None
    horizons: list[SimilarSetupHorizonMetric]
    explanation: str
    matched_attributes: list[str] = field(default_factory=list)


def descriptor_from_snapshot(snapshot: SignalValidationSnapshotRecord) -> SimilarSetupDescriptor:
    """Build a comparable setup descriptor from a persisted signal snapshot."""

    technical_context = _json_obj(snapshot.technical_context_json)
    sentiment_context = _json_obj(snapshot.sentiment_context_json)
    pattern_context = _json_obj(snapshot.pattern_context_json)
    return SimilarSetupDescriptor(
        symbol=snapshot.symbol,
        action=snapshot.final_action,
        confidence_bucket=_confidence_bucket(snapshot.confidence),
        risk_grade=snapshot.risk_grade,
        regime_label=snapshot.regime_label,
        preferred_horizon=snapshot.preferred_horizon,
        technical_direction=_str_or_none(technical_context.get("trend_direction")),
        sentiment_direction=_str_or_none(sentiment_context.get("label")),
        pattern_behavior=(
            _str_or_none(pattern_context.get("trend_character"))
            or _str_or_none(pattern_context.get("overall_direction"))
        ),
        blocker_state="blocked" if snapshot.signal_ignored_or_blocked or snapshot.blocker_reasons else "clear",
    )


def build_similar_setup_report(
    *,
    current_setup: SimilarSetupDescriptor,
    snapshots: list[SignalValidationSnapshotRecord],
    candles_by_symbol: dict[str, list[HistoricalCandleRecord]],
    exclude_snapshot_id: int | None = None,
    horizon: str | None = None,
) -> SimilarSetupReport:
    """Compare a current setup against historically similar evaluated signals."""

    candidates = [
        snapshot
        for snapshot in snapshots
        if exclude_snapshot_id is None or snapshot.id != exclude_snapshot_id
    ]
    scored = [
        (snapshot, _similarity_score(current_setup, descriptor_from_snapshot(snapshot)))
        for snapshot in candidates
    ]
    scored = [(snapshot, score) for snapshot, score in scored if score >= _minimum_similarity_score(current_setup)]
    matched = [snapshot for snapshot, _ in scored]
    outcomes = evaluate_signal_outcomes(snapshots=matched, candles_by_symbol=candles_by_symbol)
    if horizon is not None:
        outcomes = [item for item in outcomes if item.horizon == horizon]
    directional = [item for item in outcomes if item.directional_return_pct is not None]
    selected_horizons = [horizon] if horizon in VALIDATION_HORIZONS else list(VALIDATION_HORIZONS.keys())
    horizon_metrics = [
        _horizon_metric(name, [item for item in directional if item.horizon == name])
        for name in selected_horizons
    ]
    best = _best_horizon(horizon_metrics)
    if len(directional) < MIN_SIMILAR_DIRECTIONAL_SAMPLES:
        return SimilarSetupReport(
            status="insufficient_data",
            reliability_label="insufficient_data",
            matching_sample_size=len(directional),
            best_horizon=best.horizon if best is not None else None,
            horizons=horizon_metrics,
            explanation=(
                f"Only {len(directional)} evaluated similar outcomes are available. "
                f"At least {MIN_SIMILAR_DIRECTIONAL_SAMPLES} are needed before judging this setup."
            ),
            matched_attributes=_matched_attributes(scored, current_setup),
        )
    reliability = _reliability_label(directional)
    return SimilarSetupReport(
        status="ready",
        reliability_label=reliability,
        matching_sample_size=len(directional),
        best_horizon=best.horizon if best is not None else None,
        horizons=horizon_metrics,
        explanation=_explanation(reliability=reliability, sample_size=len(directional), best=best),
        matched_attributes=_matched_attributes(scored, current_setup),
    )


def _similarity_score(current: SimilarSetupDescriptor, historical: SimilarSetupDescriptor) -> int:
    score = 0
    score += _match_points(current.symbol, historical.symbol, 3)
    score += _match_points(current.action, historical.action, 4)
    score += _match_points(current.confidence_bucket, historical.confidence_bucket, 2)
    score += _match_points(current.risk_grade, historical.risk_grade, 2)
    score += _match_points(current.regime_label, historical.regime_label, 3)
    score += _match_points(current.preferred_horizon, historical.preferred_horizon, 1)
    score += _match_points(current.technical_direction, historical.technical_direction, 2)
    score += _match_points(current.sentiment_direction, historical.sentiment_direction, 1)
    score += _match_points(current.pattern_behavior, historical.pattern_behavior, 1)
    score += _match_points(current.blocker_state, historical.blocker_state, 2)
    return score


def _minimum_similarity_score(current: SimilarSetupDescriptor) -> int:
    available = sum(
        1
        for value in (
            current.symbol,
            current.action,
            current.confidence_bucket,
            current.risk_grade,
            current.regime_label,
            current.preferred_horizon,
            current.technical_direction,
            current.sentiment_direction,
            current.pattern_behavior,
            current.blocker_state,
        )
        if value is not None
    )
    return 9 if available >= 7 else 6


def _match_points(current: str | None, historical: str | None, points: int) -> int:
    if current is None or historical is None:
        return 0
    return points if current == historical else 0


def _horizon_metric(horizon: str, outcomes: list[SignalOutcome]) -> SimilarSetupHorizonMetric:
    wins = [item for item in outcomes if item.survived_fees_slippage]
    return SimilarSetupHorizonMetric(
        horizon=horizon,
        sample_size=len(outcomes),
        win_rate_pct=_rate(len(wins), len(outcomes)),
        expectancy_pct=_avg([item.directional_return_pct for item in outcomes if item.directional_return_pct is not None]),
        average_favorable_move_pct=_avg([item.max_favorable_move_pct for item in outcomes]),
        average_adverse_move_pct=_avg([item.max_adverse_move_pct for item in outcomes]),
    )


def _best_horizon(metrics: list[SimilarSetupHorizonMetric]) -> SimilarSetupHorizonMetric | None:
    candidates = [item for item in metrics if item.expectancy_pct is not None and item.sample_size > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.expectancy_pct or Decimal("-999"), item.sample_size))


def _reliability_label(outcomes: list[SignalOutcome]):
    wins = [item for item in outcomes if item.survived_fees_slippage]
    win_rate = _rate(len(wins), len(outcomes)) or Decimal("0")
    expectancy = _avg([item.directional_return_pct for item in outcomes if item.directional_return_pct is not None]) or Decimal("0")
    if len(outcomes) >= 10 and win_rate >= Decimal("60") and expectancy > Decimal("0"):
        return "strong"
    if len(outcomes) >= 5 and win_rate >= Decimal("55") and expectancy > Decimal("0"):
        return "promising"
    if expectancy < Decimal("0") or win_rate < Decimal("45"):
        return "weak"
    return "mixed"


def _explanation(
    *,
    reliability: str,
    sample_size: int,
    best: SimilarSetupHorizonMetric | None,
) -> str:
    if best is None or best.expectancy_pct is None:
        return f"{sample_size} similar evaluated outcomes were found, but no horizon has a clear measured edge yet."
    return (
        f"{sample_size} similar evaluated outcomes were found. "
        f"The best measured horizon is {best.horizon} with {best.expectancy_pct}% expectancy. "
        f"Reliability is {reliability}."
    )


def _matched_attributes(scored: list[tuple[SignalValidationSnapshotRecord, int]], current: SimilarSetupDescriptor) -> list[str]:
    if not scored:
        return []
    descriptors = [descriptor_from_snapshot(snapshot) for snapshot, _ in scored]
    matched: list[str] = []
    for field_name, label in (
        ("symbol", "symbol"),
        ("action", "action"),
        ("confidence_bucket", "confidence bucket"),
        ("risk_grade", "risk grade"),
        ("regime_label", "regime"),
        ("preferred_horizon", "preferred horizon"),
        ("technical_direction", "technical direction"),
        ("sentiment_direction", "sentiment direction"),
        ("pattern_behavior", "pattern behavior"),
        ("blocker_state", "blocker state"),
    ):
        current_value = getattr(current, field_name)
        if current_value is None:
            continue
        if any(getattr(descriptor, field_name) == current_value for descriptor in descriptors):
            matched.append(label)
    return matched


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


def _confidence_bucket(confidence: int) -> str:
    if confidence >= 70:
        return "high"
    if confidence >= 45:
        return "medium"
    return "low"


def _json_obj(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _str_or_none(value) -> str | None:
    return str(value) if value is not None else None
