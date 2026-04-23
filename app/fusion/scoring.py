"""Scoring helpers for the unified signal fusion engine."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.fusion.models import FinalSignal, FusionInputs, FusionSignalSnapshot, PreferredHorizon, RiskGrade
from app.fusion.weights import FusionWeights


def build_fusion_signal(
    *,
    inputs: FusionInputs,
    weights: FusionWeights,
) -> FusionSignalSnapshot:
    """Score one unified advisory signal from the currently available inputs."""

    generated_at = _generated_at(inputs)
    technical_score, technical_reasons, technical_warnings = _technical_signal(inputs)
    pattern_score, pattern_reasons, pattern_warnings = _pattern_signal(inputs)
    ai_score, ai_reasons, ai_warnings = _ai_signal(inputs)
    sentiment_score, sentiment_reasons, sentiment_warnings = _sentiment_signal(inputs)
    readiness_score, readiness_reasons, readiness_warnings = _readiness_signal(inputs)

    weighted_score = (
        technical_score * weights.technical_weight
        + pattern_score * weights.pattern_weight
        + ai_score * weights.ai_weight
        + sentiment_score * weights.sentiment_weight
        + readiness_score * weights.readiness_weight
    )
    normalized = max(Decimal("-1"), min(Decimal("1"), weighted_score))
    alignment_score = int((abs(normalized) * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))

    warnings = tuple(
        dict.fromkeys(
            technical_warnings
            + pattern_warnings
            + ai_warnings
            + sentiment_warnings
            + readiness_warnings
        )
    )
    reasons = tuple(
        list(
            dict.fromkeys(
                technical_reasons
                + pattern_reasons
                + ai_reasons
                + sentiment_reasons
                + readiness_reasons
            )
        )[:4]
    )
    preferred_horizon = _preferred_horizon(inputs)
    expected_edge_pct = inputs.trade_readiness.expected_edge_pct if inputs.trade_readiness is not None else None
    risk_grade = _risk_grade(inputs, warnings)
    final_signal = _final_signal(inputs, normalized, warnings)
    confidence = _confidence(inputs, normalized, warnings, final_signal)

    return FusionSignalSnapshot(
        symbol=inputs.symbol,
        generated_at=generated_at,
        data_state="ready",
        status_message=f"Fusion signal is ready for {inputs.symbol}.",
        final_signal=final_signal,
        confidence=confidence,
        expected_edge_pct=expected_edge_pct,
        preferred_horizon=preferred_horizon,
        risk_grade=risk_grade,
        alignment_score=alignment_score,
        top_reasons=reasons,
        warnings=warnings,
        invalidation_hint=_invalidation_hint(inputs, final_signal),
    )


def _technical_signal(inputs: FusionInputs) -> tuple[Decimal, list[str], list[str]]:
    """Score technical alignment into a directional fusion component."""

    technical = inputs.technical_analysis
    if technical is None or technical.data_state != "ready" or technical.trend_direction is None:
        return Decimal("0"), [], ["Technical trend context is incomplete."]

    reasons: list[str] = []
    warnings: list[str] = []
    direction_score = _direction_to_score(technical.trend_direction)
    strength_multiplier = Decimal(str(technical.trend_strength_score or 0)) / Decimal("100")
    score = direction_score * strength_multiplier
    reasons.append(
        f"Technical trend is {technical.trend_direction} with {technical.trend_strength or 'unknown'} strength."
    )

    if technical.multi_timeframe_agreement in {"bullish_alignment", "bearish_alignment"}:
        score *= Decimal("1.10")
        reasons.append(f"Derived timeframe agreement is {technical.multi_timeframe_agreement.replace('_', ' ')}.")
    elif technical.multi_timeframe_agreement == "mixed":
        score *= Decimal("0.65")
        warnings.append("Timeframe alignment is mixed.")

    if technical.breakout_readiness == "high" and technical.breakout_bias == "upside":
        score += Decimal("0.10")
        reasons.append("Breakout readiness is high to the upside.")
    if technical.breakout_readiness == "high" and technical.breakout_bias == "downside":
        score -= Decimal("0.10")
        reasons.append("Breakout readiness is high to the downside.")

    if technical.reversal_risk == "high":
        score *= Decimal("0.60")
        warnings.append("Reversal risk is elevated.")
    if technical.volatility_regime == "high":
        warnings.append("Technical volatility regime is high.")

    return max(Decimal("-1"), min(Decimal("1"), score)), reasons, warnings


def _pattern_signal(inputs: FusionInputs) -> tuple[Decimal, list[str], list[str]]:
    """Score multi-horizon pattern context into the fusion model."""

    pattern = inputs.pattern_analysis
    if pattern is None or pattern.data_state != "ready" or pattern.overall_direction is None:
        return Decimal("0"), [], ["Pattern context is incomplete."]

    reasons: list[str] = []
    warnings: list[str] = []
    score = _direction_to_score(pattern.overall_direction) * Decimal("0.75")
    if pattern.net_return_pct is not None:
        score += max(Decimal("-0.20"), min(Decimal("0.20"), pattern.net_return_pct / Decimal("20")))
    reasons.append(
        f"{pattern.horizon.upper()} pattern direction is {pattern.overall_direction} with net return "
        f"{pattern.net_return_pct if pattern.net_return_pct is not None else Decimal('0')}%."
    )

    if pattern.trend_character == "persistent":
        score *= Decimal("1.10")
        reasons.append("Pattern trend character is persistent.")
    elif pattern.trend_character == "choppy":
        score *= Decimal("0.55")
        warnings.append("Pattern behavior is choppy.")

    if pattern.breakout_tendency == "range_bound":
        warnings.append("Pattern context is range-bound.")
    if pattern.reversal_tendency == "elevated":
        warnings.append("Pattern reversal tendency is elevated.")

    return max(Decimal("-1"), min(Decimal("1"), score)), reasons, warnings


def _ai_signal(inputs: FusionInputs) -> tuple[Decimal, list[str], list[str]]:
    """Score the advisory AI signal into the fusion model."""

    signal = inputs.ai_signal
    if signal is None:
        return Decimal("0"), [], ["AI advisory context is unavailable."]

    reasons: list[str] = []
    warnings: list[str] = []
    score = _direction_to_score(signal.bias) * (Decimal(signal.confidence) / Decimal("100"))
    reasons.append(
        f"AI advisory bias is {signal.bias} at {signal.confidence}% confidence on {signal.preferred_horizon or '15m'}."
    )

    if signal.abstain:
        score *= Decimal("0.30")
        warnings.append("AI recommends abstaining.")
    if signal.confirmation_needed:
        score *= Decimal("0.60")
        warnings.append("AI still wants confirmation.")
    if signal.low_confidence:
        score *= Decimal("0.65")
        warnings.append("AI confidence is low.")
    if signal.regime in {"choppy", "high_volatility_unstable"}:
        score *= Decimal("0.45")
        warnings.append(f"AI regime is {signal.regime.replace('_', ' ')}.")
    if signal.regime == "breakout_building":
        reasons.append("AI sees breakout-building conditions.")
    if signal.regime == "reversal_risk":
        warnings.append("AI sees reversal risk.")

    return max(Decimal("-1"), min(Decimal("1"), score)), reasons, warnings


def _sentiment_signal(inputs: FusionInputs) -> tuple[Decimal, list[str], list[str]]:
    """Score symbol sentiment into the fusion model."""

    sentiment = inputs.symbol_sentiment
    if sentiment is None or sentiment.data_state != "ready" or sentiment.score is None:
        return Decimal("0"), [], ["Symbol sentiment is incomplete."]

    reasons: list[str] = []
    warnings: list[str] = []
    score = Decimal(sentiment.score) / Decimal("100")
    confidence_multiplier = Decimal(sentiment.confidence or 0) / Decimal("100")
    score *= max(Decimal("0.25"), confidence_multiplier)
    reasons.append(
        f"Symbol sentiment is {sentiment.label} with proxy score {sentiment.score} and {sentiment.confidence or 0}% confidence."
    )
    if sentiment.risk_flag in {"hype", "panic"}:
        warnings.append(f"Sentiment risk flag is {sentiment.risk_flag}.")
    if sentiment.momentum_state == "stable":
        score *= Decimal("0.80")
    return max(Decimal("-1"), min(Decimal("1"), score)), reasons, warnings


def _readiness_signal(inputs: FusionInputs) -> tuple[Decimal, list[str], list[str]]:
    """Score deterministic trade readiness and cost gating into the fusion model."""

    readiness = inputs.trade_readiness
    if readiness is None:
        return Decimal("0"), [], ["Trade readiness is unavailable."]

    reasons: list[str] = []
    warnings: list[str] = []
    score = Decimal("0")

    if not readiness.runtime_active:
        warnings.append("Runtime is not active for this symbol.")
    if not readiness.enough_candle_history:
        warnings.append("Not enough candle history for deterministic readiness.")
    if readiness.risk_ready:
        score += Decimal("0.45")
        reasons.append("Deterministic risk checks currently approve or allow resizing.")
    if readiness.risk_blocked:
        score -= Decimal("0.50")
        warnings.append("Deterministic risk checks are blocking trades.")
    if readiness.deterministic_entry_signal:
        score += Decimal("0.20")
        reasons.append("Deterministic entry signal is active.")
    if readiness.deterministic_exit_signal:
        score -= Decimal("0.20")
        reasons.append("Deterministic exit signal is active.")
    if not readiness.broker_ready:
        warnings.append("Paper broker is not ready for execution.")
    if readiness.expected_edge_pct is not None and readiness.estimated_round_trip_cost_pct is not None:
        if readiness.expected_edge_pct <= readiness.estimated_round_trip_cost_pct:
            score -= Decimal("0.45")
            warnings.append("Expected edge does not clear round-trip costs.")
        else:
            reasons.append("Expected edge clears estimated round-trip costs.")

    return max(Decimal("-1"), min(Decimal("1"), score)), reasons, warnings


def _final_signal(
    inputs: FusionInputs,
    normalized_score: Decimal,
    warnings: tuple[str, ...],
) -> FinalSignal:
    """Map the fused score and safety warnings into one final advisory action."""

    readiness = inputs.trade_readiness
    has_long_position = inputs.current_position_quantity > Decimal("0")
    has_short_position = inputs.current_position_quantity < Decimal("0")

    if any(
        warning in warnings
        for warning in (
            "Technical volatility regime is high.",
            "AI regime is high volatility unstable.",
        )
    ):
        return "reduce_risk"

    if has_long_position and (normalized_score <= Decimal("-0.18") or (readiness is not None and readiness.deterministic_exit_signal)):
        return "exit_long"
    if has_short_position and normalized_score >= Decimal("0.18"):
        return "exit_short"
    if readiness is not None and readiness.risk_blocked:
        return "wait"
    if normalized_score >= Decimal("0.28"):
        return "long"
    if normalized_score <= Decimal("-0.28"):
        return "short"
    return "wait"


def _confidence(
    inputs: FusionInputs,
    normalized_score: Decimal,
    warnings: tuple[str, ...],
    final_signal: FinalSignal,
) -> int:
    """Shape fusion confidence from alignment and disagreement."""

    base = int((abs(normalized_score) * Decimal("70")).to_integral_value(rounding=ROUND_HALF_UP))
    available_inputs = sum(
        1
        for item in (
            inputs.technical_analysis,
            inputs.pattern_analysis,
            inputs.ai_signal,
            inputs.symbol_sentiment,
            inputs.trade_readiness,
        )
        if item is not None
    )
    base += min(20, available_inputs * 4)
    base -= min(35, len(warnings) * 6)
    if final_signal in {"wait", "reduce_risk"}:
        base = min(base, 58)
    return max(5, min(95, base))


def _risk_grade(inputs: FusionInputs, warnings: tuple[str, ...]) -> RiskGrade:
    """Classify operator-facing risk grade from current context."""

    risk_points = 0
    technical = inputs.technical_analysis
    if technical is not None and technical.volatility_regime == "high":
        risk_points += 2
    ai_signal = inputs.ai_signal
    if ai_signal is not None and ai_signal.regime in {"choppy", "high_volatility_unstable", "reversal_risk"}:
        risk_points += 2
    if len(warnings) >= 3:
        risk_points += 1
    if inputs.trade_readiness is not None and inputs.trade_readiness.risk_blocked:
        risk_points += 2
    if risk_points >= 4:
        return "high"
    if risk_points >= 2:
        return "medium"
    return "low"


def _preferred_horizon(inputs: FusionInputs) -> PreferredHorizon:
    """Select the most credible execution horizon from current context."""

    if inputs.ai_signal is not None and inputs.ai_signal.preferred_horizon is not None:
        return inputs.ai_signal.preferred_horizon
    technical = inputs.technical_analysis
    if technical is not None and technical.multi_timeframe_agreement in {"bullish_alignment", "bearish_alignment"}:
        return "15m"
    pattern = inputs.pattern_analysis
    if pattern is not None and pattern.trend_character == "persistent":
        return "1h"
    return "5m"


def _invalidation_hint(inputs: FusionInputs, final_signal: FinalSignal) -> str | None:
    """Return a concise invalidation hint from support/resistance and regime."""

    technical = inputs.technical_analysis
    if technical is None:
        return None
    if final_signal == "long" and technical.support_levels:
        return f"Invalidate the long idea if price loses support near {technical.support_levels[0]}."
    if final_signal == "short" and technical.resistance_levels:
        return f"Invalidate the short idea if price reclaims resistance near {technical.resistance_levels[0]}."
    if final_signal == "exit_long":
        return "Exit-long bias weakens if bullish structure and entry alignment rebuild."
    if final_signal == "reduce_risk":
        return "Risk can normalize after volatility contracts and alignment improves."
    return None


def _generated_at(inputs: FusionInputs):
    """Pick the best available generation timestamp for the fusion snapshot."""

    for candidate in (
        inputs.ai_signal.feature_vector.timestamp if inputs.ai_signal is not None else None,
        inputs.technical_analysis.timestamp if inputs.technical_analysis is not None else None,
        inputs.pattern_analysis.generated_at if inputs.pattern_analysis is not None else None,
        inputs.symbol_sentiment.generated_at if inputs.symbol_sentiment is not None else None,
    ):
        if candidate is not None:
            return candidate
    from datetime import UTC, datetime

    return datetime.now(tz=UTC)


def _direction_to_score(direction: str | None) -> Decimal:
    """Map a bullish/bearish/sideways label to a normalized directional score."""

    if direction == "bullish":
        return Decimal("1")
    if direction == "bearish":
        return Decimal("-1")
    return Decimal("0")
