"""Advisory trade eligibility checks from measured signal evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.monitoring.signal_validation import HorizonQualityMetric, SignalValidationReport
from app.monitoring.similar_setups import SimilarSetupReport


EligibilityStatus = Literal["eligible", "not_eligible", "watch_only", "insufficient_data"]
EvidenceStrength = Literal["insufficient", "weak", "mixed", "promising", "strong"]

MIN_VALIDATION_HORIZON_SAMPLES = 5


@dataclass(slots=True)
class TradeEligibilityInput:
    """Current signal and evidence used by the advisory eligibility gate."""

    symbol: str
    action: str
    confidence: int
    risk_grade: str
    preferred_horizon: str | None
    expected_edge_pct: Decimal | None
    estimated_cost_pct: Decimal | None
    blocker_reasons: tuple[str, ...]
    current_warnings: tuple[str, ...]
    regime_label: str | None
    regime_confidence: int | None
    regime_warnings: tuple[str, ...]
    regime_avoid_conditions: tuple[str, ...]
    similar_setup: SimilarSetupReport | None
    signal_validation: SignalValidationReport | None


@dataclass(slots=True)
class TradeEligibilityResult:
    """Advisory-only trade eligibility result."""

    status: EligibilityStatus
    evidence_strength: EvidenceStrength
    reason: str
    required_confirmations: list[str] = field(default_factory=list)
    minimum_confidence_threshold: int = 75
    preferred_horizon: str | None = None
    conditions_to_avoid: list[str] = field(default_factory=list)
    blocker_summary: str = "No current blockers."
    similar_setup_summary: str = "No similar-setup evidence is available yet."
    regime_summary: str = "No regime analysis is available yet."
    fee_slippage_summary: str = "No fee/slippage edge estimate is available yet."
    warnings: list[str] = field(default_factory=list)


def evaluate_trade_eligibility(context: TradeEligibilityInput) -> TradeEligibilityResult:
    """Return an advisory-only eligibility read from measured evidence."""

    evidence_strength = _evidence_strength(context.similar_setup)
    minimum_confidence = _minimum_confidence_threshold(evidence_strength)
    horizon_metric = _selected_horizon_metric(context.signal_validation, context.preferred_horizon)
    blocker_summary = _blocker_summary(context.blocker_reasons)
    similar_summary = _similar_setup_summary(context.similar_setup)
    regime_summary = _regime_summary(context)
    fee_summary = _fee_slippage_summary(context.expected_edge_pct, context.estimated_cost_pct)
    warnings = list(dict.fromkeys((*context.current_warnings, *context.regime_warnings)))
    conditions_to_avoid = list(dict.fromkeys((*context.regime_avoid_conditions, *_risk_conditions(context))))
    required_confirmations = _base_confirmations(context, minimum_confidence)

    if context.blocker_reasons:
        return TradeEligibilityResult(
            status="not_eligible",
            evidence_strength=evidence_strength,
            reason="Current blockers prevent this signal from being considered for paper automation.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if _edge_fails_cost_check(context.expected_edge_pct, context.estimated_cost_pct):
        return TradeEligibilityResult(
            status="not_eligible",
            evidence_strength=evidence_strength,
            reason="Expected edge does not clear estimated fees and slippage.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if context.risk_grade == "high" or _regime_is_bad_for_action(context.regime_label, context.action):
        return TradeEligibilityResult(
            status="not_eligible",
            evidence_strength=evidence_strength,
            reason="Risk grade or current regime is too unfavorable for paper automation consideration.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if _insufficient_evidence(context.similar_setup, context.signal_validation, horizon_metric):
        return TradeEligibilityResult(
            status="insufficient_data",
            evidence_strength="insufficient",
            reason="There is not enough measured signal history to judge automation eligibility honestly.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if context.action not in {"buy", "sell_exit"}:
        return TradeEligibilityResult(
            status="watch_only",
            evidence_strength=evidence_strength,
            reason="The current assistant decision is not an actionable paper entry or exit.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if evidence_strength == "weak" or _horizon_expectancy(horizon_metric) <= Decimal("0"):
        return TradeEligibilityResult(
            status="not_eligible",
            evidence_strength=evidence_strength,
            reason="Measured outcomes for this setup or horizon do not support automation consideration.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    if evidence_strength == "mixed" or context.confidence < minimum_confidence:
        return TradeEligibilityResult(
            status="watch_only",
            evidence_strength=evidence_strength,
            reason="The setup has some support, but evidence or confidence is not strong enough yet.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
        )

    return TradeEligibilityResult(
        status="eligible",
        evidence_strength=evidence_strength,
        reason="Current signal, regime, similar setups, and fee/slippage evidence support paper automation consideration.",
        required_confirmations=required_confirmations,
        minimum_confidence_threshold=minimum_confidence,
        preferred_horizon=context.preferred_horizon,
        conditions_to_avoid=conditions_to_avoid,
        blocker_summary=blocker_summary,
        similar_setup_summary=similar_summary,
        regime_summary=regime_summary,
        fee_slippage_summary=fee_summary,
        warnings=warnings,
    )


def _evidence_strength(report: SimilarSetupReport | None) -> EvidenceStrength:
    if report is None or report.status == "insufficient_data":
        return "insufficient"
    return report.reliability_label


def _minimum_confidence_threshold(strength: EvidenceStrength) -> int:
    if strength == "strong":
        return 65
    if strength == "promising":
        return 70
    if strength == "mixed":
        return 75
    return 80


def _selected_horizon_metric(
    report: SignalValidationReport | None,
    preferred_horizon: str | None,
) -> HorizonQualityMetric | None:
    if report is None or not report.horizons:
        return None
    if preferred_horizon is not None:
        match = next((item for item in report.horizons if item.horizon == preferred_horizon), None)
        if match is not None:
            return match
    return max(report.horizons, key=lambda item: (item.expectancy_pct or Decimal("-999"), item.sample_size))


def _insufficient_evidence(
    similar_setup: SimilarSetupReport | None,
    validation: SignalValidationReport | None,
    horizon_metric: HorizonQualityMetric | None,
) -> bool:
    if similar_setup is None or similar_setup.status == "insufficient_data":
        return True
    if validation is None or validation.status == "insufficient_data":
        return True
    if horizon_metric is None:
        return True
    return horizon_metric.actionable_sample_size < MIN_VALIDATION_HORIZON_SAMPLES


def _horizon_expectancy(metric: HorizonQualityMetric | None) -> Decimal:
    if metric is None or metric.expectancy_pct is None:
        return Decimal("0")
    return metric.expectancy_pct


def _edge_fails_cost_check(
    expected_edge_pct: Decimal | None,
    estimated_cost_pct: Decimal | None,
) -> bool:
    if expected_edge_pct is None or estimated_cost_pct is None:
        return False
    return expected_edge_pct <= estimated_cost_pct


def _regime_is_bad_for_action(regime_label: str | None, action: str) -> bool:
    if regime_label in {"low_liquidity", "choppy", "high_volatility"}:
        return True
    if action == "buy" and regime_label in {"trending_down", "reversal_risk"}:
        return True
    return False


def _risk_conditions(context: TradeEligibilityInput) -> tuple[str, ...]:
    conditions: list[str] = []
    if context.risk_grade == "high":
        conditions.append("high risk grade")
    if _regime_is_bad_for_action(context.regime_label, context.action):
        conditions.append(f"{context.regime_label} regime")
    if _edge_fails_cost_check(context.expected_edge_pct, context.estimated_cost_pct):
        conditions.append("expected edge below estimated costs")
    return tuple(conditions)


def _base_confirmations(context: TradeEligibilityInput, minimum_confidence: int) -> list[str]:
    confirmations = [
        "Current blockers remain clear.",
        "Expected edge remains above estimated fees and slippage.",
    ]
    if context.confidence < minimum_confidence:
        confirmations.append(f"Confidence improves to at least {minimum_confidence}%.")
    if context.regime_label in {"sideways", "breakout_building", "reversal_risk"}:
        confirmations.append("Next candle confirms direction instead of rejecting the setup.")
    return confirmations


def _blocker_summary(blockers: tuple[str, ...]) -> str:
    if not blockers:
        return "No current blockers."
    return "; ".join(blockers)


def _similar_setup_summary(report: SimilarSetupReport | None) -> str:
    if report is None:
        return "No similar-setup evidence is available yet."
    return f"{report.reliability_label}: {report.explanation}"


def _regime_summary(context: TradeEligibilityInput) -> str:
    if context.regime_label is None:
        return "No regime analysis is available yet."
    confidence = context.regime_confidence if context.regime_confidence is not None else 0
    return f"{context.regime_label} regime with {confidence}% confidence."


def _fee_slippage_summary(
    expected_edge_pct: Decimal | None,
    estimated_cost_pct: Decimal | None,
) -> str:
    if expected_edge_pct is None or estimated_cost_pct is None:
        return "No fee/slippage edge estimate is available yet."
    if expected_edge_pct <= estimated_cost_pct:
        return f"Expected edge {expected_edge_pct}% does not clear estimated cost {estimated_cost_pct}%."
    return f"Expected edge {expected_edge_pct}% clears estimated cost {estimated_cost_pct}%."
