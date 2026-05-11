"""Advisory trade eligibility checks from measured signal evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.monitoring.signal_validation import HorizonQualityMetric, SignalValidationReport
from app.monitoring.similar_setups import SimilarSetupReport
from app.monitoring.liquidity_bias import LiquidityBiasSnapshot
from app.monitoring.liquidity_zones import LiquidityZoneSnapshot
from app.monitoring.crowd_positioning import CrowdPositioningSnapshot
from app.monitoring.liquidation_intelligence import LiquidationIntelligenceSnapshot


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
    liquidity_bias: LiquidityBiasSnapshot | None = None
    liquidity_zones: LiquidityZoneSnapshot | None = None
    crowd_positioning: CrowdPositioningSnapshot | None = None
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: str = "neutral"
    liquidation_intelligence: LiquidationIntelligenceSnapshot | None = None


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
    liquidity_zone_summary: str = "No liquidity-zone estimate is available yet."
    sweep_risk: str = "none"
    trade_timing_adjustment: str = "wait_for_confirmation"
    tp_sl_alignment: str = "needs_review"
    crowd_side: str = "balanced"
    crowd_strength: str = "low"
    squeeze_risk: str = "low"
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: str = "neutral"
    liquidation_signal: str = "none"
    liquidation_intensity: str = "low"
    dominant_side: str = "balanced"


def evaluate_trade_eligibility(context: TradeEligibilityInput) -> TradeEligibilityResult:
    """Return an advisory-only eligibility read from measured evidence."""

    evidence_strength = _evidence_strength(context.similar_setup)
    minimum_confidence = _liquidation_adjusted_minimum_confidence(
        context=context,
        threshold=_minimum_confidence_threshold(evidence_strength),
    )
    horizon_metric = _selected_horizon_metric(context.signal_validation, context.preferred_horizon)
    blocker_summary = _blocker_summary(context.blocker_reasons)
    similar_summary = _similar_setup_summary(context.similar_setup)
    regime_summary = _regime_summary(context)
    fee_summary = _fee_slippage_summary(context.expected_edge_pct, context.estimated_cost_pct)
    warnings = list(
        dict.fromkeys(
            (
                *context.current_warnings,
                *context.regime_warnings,
                *_liquidity_warnings(context),
                *_zone_warnings(context),
                *_crowd_warnings(context),
                *_liquidation_warnings(context),
            )
        )
    )
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
        )

    if _crowd_blocks_action(context):
        return TradeEligibilityResult(
            status="watch_only",
            evidence_strength=evidence_strength,
            reason="Binance funding and open-interest crowd positioning makes this setup watch-only.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
        )

    if _liquidation_blocks_action(context):
        status: EligibilityStatus = "not_eligible" if _liquidation_wrong_way_cascade(context) else "watch_only"
        return TradeEligibilityResult(
            status=status,
            evidence_strength=evidence_strength,
            reason="Recent liquidation-event intelligence conflicts with the current paper setup.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
        )

    if _liquidity_zones_block_action(context):
        status: EligibilityStatus = (
            "not_eligible"
            if context.liquidity_zones is not None and context.liquidity_zones.trade_timing_adjustment == "avoid_chop"
            else "watch_only"
        )
        return TradeEligibilityResult(
            status=status,
            evidence_strength=evidence_strength,
            reason="Estimated liquidity zones make this setup too early or poorly placed for paper automation consideration.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
        )

    if _liquidity_conflicts_with_action(context):
        return TradeEligibilityResult(
            status="watch_only",
            evidence_strength=evidence_strength,
            reason="Estimated liquidity positioning conflicts with the current paper signal, so this remains watch-only.",
            required_confirmations=required_confirmations,
            minimum_confidence_threshold=minimum_confidence,
            preferred_horizon=context.preferred_horizon,
            conditions_to_avoid=conditions_to_avoid,
            blocker_summary=blocker_summary,
            similar_setup_summary=similar_summary,
            regime_summary=regime_summary,
            fee_slippage_summary=fee_summary,
            warnings=warnings,
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
            **_zone_result_fields(context),
            **_crowd_result_fields(context),
            **_liquidation_result_fields(context),
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
        **_zone_result_fields(context),
        **_crowd_result_fields(context),
        **_liquidation_result_fields(context),
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


def _liquidation_adjusted_minimum_confidence(
    *,
    context: TradeEligibilityInput,
    threshold: int,
) -> int:
    if _liquidation_sweep_confirmation(context):
        return max(60, threshold - 3)
    return threshold


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
    if context.liquidity_zones is not None:
        if context.liquidity_zones.trade_timing_adjustment == "avoid_chop":
            conditions.append("choppy both-side liquidity")
        if context.liquidity_zones.trade_timing_adjustment == "wait_for_sweep" and not _liquidation_sweep_confirmation(context):
            conditions.append("wait for liquidity sweep")
        if context.liquidity_zones.tp_sl_alignment == "stop_too_close_to_liquidity":
            conditions.append("stop too close to estimated liquidity")
    liquidity = context.liquidity_bias
    if liquidity is not None:
        if context.action == "buy" and liquidity.trap_risk == "long_trap":
            conditions.append("long liquidation trap risk")
        if context.action == "sell_exit" and liquidity.trap_risk == "short_trap":
            conditions.append("short squeeze risk")
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
    if _liquidity_conflicts_with_action(context):
        confirmations.append("Liquidity sweep risk cools or price confirms through the trap area.")
    if context.liquidity_zones is not None and context.liquidity_zones.tp_sl_alignment == "stop_too_close_to_liquidity":
        confirmations.append("Stop placement moves away from the estimated liquidity zone.")
    return confirmations


def _liquidity_warnings(context: TradeEligibilityInput) -> tuple[str, ...]:
    liquidity = context.liquidity_bias
    if liquidity is None or liquidity.liquidity_pressure == "low":
        return ()
    return (liquidity.explanation,)


def _liquidity_conflicts_with_action(context: TradeEligibilityInput) -> bool:
    liquidity = context.liquidity_bias
    if liquidity is None or liquidity.liquidity_pressure != "high":
        return False
    if context.action == "buy" and liquidity.trap_risk == "long_trap":
        return True
    if context.action == "sell_exit" and liquidity.trap_risk == "short_trap":
        return True
    return False


def _crowd_blocks_action(context: TradeEligibilityInput) -> bool:
    crowd = context.crowd_positioning
    if crowd is None or crowd.crowd_strength != "high":
        return False
    if context.action == "buy" and crowd.crowd_side == "long_crowded":
        return True
    if context.action == "sell_exit" and crowd.crowd_side == "short_crowded":
        return True
    return False


def _crowd_warnings(context: TradeEligibilityInput) -> tuple[str, ...]:
    crowd = context.crowd_positioning
    if crowd is None or crowd.crowd_strength == "low":
        return ()
    return (crowd.explanation,)


def _liquidation_warnings(context: TradeEligibilityInput) -> tuple[str, ...]:
    liquidation = context.liquidation_intelligence
    if liquidation is None or liquidation.liquidation_signal in {"none", "noise"}:
        return ()
    return (liquidation.explanation,)


def _liquidation_blocks_action(context: TradeEligibilityInput) -> bool:
    liquidation = context.liquidation_intelligence
    if liquidation is None:
        return False
    if _liquidation_wrong_way_cascade(context):
        return True
    return liquidation.liquidation_signal == "exhaustion"


def _liquidation_wrong_way_cascade(context: TradeEligibilityInput) -> bool:
    liquidation = context.liquidation_intelligence
    if liquidation is None:
        return False
    if context.action == "buy" and liquidation.liquidation_signal == "cascade_down":
        return True
    if context.action == "sell_exit" and liquidation.liquidation_signal == "cascade_up":
        return True
    return False


def _liquidation_sweep_confirmation(context: TradeEligibilityInput) -> bool:
    liquidation = context.liquidation_intelligence
    return liquidation is not None and liquidation.liquidation_signal == "sweep_confirmation"


def _zone_warnings(context: TradeEligibilityInput) -> tuple[str, ...]:
    zones = context.liquidity_zones
    if zones is None:
        return ()
    warnings: list[str] = []
    if zones.sweep_risk != "none":
        warnings.append(zones.explanation)
    if zones.tp_sl_alignment == "stop_too_close_to_liquidity":
        warnings.append("Estimated liquidity zone is close to the proposed stop.")
    return tuple(warnings)


def _liquidity_zones_block_action(context: TradeEligibilityInput) -> bool:
    zones = context.liquidity_zones
    if zones is None:
        return False
    if zones.trade_timing_adjustment == "wait_for_sweep" and _liquidation_sweep_confirmation(context):
        return zones.tp_sl_alignment == "stop_too_close_to_liquidity"
    return zones.trade_timing_adjustment in {"avoid_chop", "wait_for_sweep"} or zones.tp_sl_alignment == "stop_too_close_to_liquidity"


def _zone_result_fields(context: TradeEligibilityInput) -> dict[str, str]:
    zones = context.liquidity_zones
    if zones is None:
        return {}
    return {
        "liquidity_zone_summary": zones.explanation,
        "sweep_risk": zones.sweep_risk,
        "trade_timing_adjustment": zones.trade_timing_adjustment,
        "tp_sl_alignment": zones.tp_sl_alignment,
    }


def _crowd_result_fields(context: TradeEligibilityInput) -> dict[str, object]:
    crowd = context.crowd_positioning
    fields: dict[str, object] = {
        "funding_rate": context.funding_rate,
        "open_interest": context.open_interest,
        "oi_trend": context.oi_trend,
    }
    if crowd is None:
        return fields
    return {
        **fields,
        "crowd_side": crowd.crowd_side,
        "crowd_strength": crowd.crowd_strength,
        "squeeze_risk": crowd.squeeze_risk,
    }


def _liquidation_result_fields(context: TradeEligibilityInput) -> dict[str, object]:
    liquidation = context.liquidation_intelligence
    if liquidation is None:
        return {}
    return {
        "liquidation_signal": liquidation.liquidation_signal,
        "liquidation_intensity": liquidation.liquidation_intensity,
        "dominant_side": liquidation.dominant_side,
    }


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
