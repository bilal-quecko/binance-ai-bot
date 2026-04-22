"""Horizon-specific advisory scoring."""

from __future__ import annotations

from decimal import Decimal

from app.ai.calibration import shape_confidence
from app.ai.models import AIFeatureVector, AIHorizonSignal, AIRegime, SuggestedAction
from app.ai.noise_filters import NoiseFilterDecision


def score_horizons(
    features: AIFeatureVector,
    *,
    regime: AIRegime,
    noise: NoiseFilterDecision,
) -> tuple[AIHorizonSignal, ...]:
    """Build distinct 5m, 15m, and 1h advisory views."""

    return (
        _score_one_horizon(features, horizon="5m", regime=regime, noise=noise),
        _score_one_horizon(features, horizon="15m", regime=regime, noise=noise),
        _score_one_horizon(features, horizon="1h", regime=regime, noise=noise),
    )


def _score_one_horizon(
    features: AIFeatureVector,
    *,
    horizon: str,
    regime: AIRegime,
    noise: NoiseFilterDecision,
) -> AIHorizonSignal:
    """Score one horizon with horizon-specific weighting."""

    score = Decimal("0")
    confidence = 48
    parts: list[str] = []

    if features.technical_trend_direction == "bullish":
        score += Decimal("1.8") if horizon == "1h" else Decimal("1.4")
        parts.append("trend remains bullish")
    elif features.technical_trend_direction == "bearish":
        score -= Decimal("1.8") if horizon == "1h" else Decimal("1.4")
        parts.append("trend remains bearish")

    horizon_return = _horizon_return(features, horizon)
    if horizon_return is not None:
        if horizon_return > Decimal("0.003"):
            score += Decimal("1.6") if horizon == "5m" else Decimal("1.2")
            confidence += 8
            parts.append(f"{horizon} return is positive")
        elif horizon_return < Decimal("-0.003"):
            score -= Decimal("1.6") if horizon == "5m" else Decimal("1.2")
            confidence += 8
            parts.append(f"{horizon} return is negative")

    if features.momentum_persistence is not None:
        if features.momentum_persistence >= Decimal("0.65"):
            score += Decimal("1.0")
            confidence += 6
            parts.append("momentum persistence is strong")
        elif features.momentum_persistence < Decimal("0.50"):
            confidence -= 6
            parts.append("momentum persistence is weak")

    if horizon == "5m":
        if features.microstructure_healthy:
            confidence += 5
            parts.append("microstructure looks stable")
        elif features.spread_ratio is not None:
            confidence -= 10
            parts.append("microstructure is noisy")
        if features.breakout_readiness == "high":
            score += Decimal("1.0")
            parts.append("breakout readiness is high")
    elif horizon == "15m":
        if features.multi_timeframe_agreement in {"bullish_alignment", "bearish_alignment"}:
            confidence += 6
            score += Decimal("0.8") if "bullish" in features.multi_timeframe_agreement else Decimal("-0.8")
            parts.append("multi-timeframe alignment is supportive")
        if features.technical_trend_strength_score is not None and features.technical_trend_strength_score >= 60:
            confidence += 6
            parts.append("trend strength is confirmed")
    elif horizon == "1h":
        if features.market_state == "risk_on":
            score += Decimal("0.9")
            confidence += 5
            parts.append("broader market is risk-on")
        elif features.market_state == "risk_off":
            score -= Decimal("0.9")
            confidence += 5
            parts.append("broader market is risk-off")
        if features.selected_symbol_relative_strength == "outperforming_btc":
            score += Decimal("0.8")
            parts.append("relative strength is supportive")
        elif features.selected_symbol_relative_strength == "underperforming_btc":
            score -= Decimal("0.8")
            parts.append("relative strength is lagging")

    disagreement = _component_disagreement(features)
    evidence_thin = _evidence_is_thin(features, horizon=horizon)
    confidence = shape_confidence(
        raw_confidence=confidence + _score_to_confidence(score),
        horizon=horizon,  # type: ignore[arg-type]
        regime=regime,
        noise_level=noise.noise_level,
        component_disagreement=disagreement,
        evidence_thin=evidence_thin,
        low_confidence=noise.low_confidence,
        confirmation_needed=noise.confirmation_needed,
    )

    if score >= Decimal("1.8"):
        bias = "bullish"
    elif score <= Decimal("-1.8"):
        bias = "bearish"
    else:
        bias = "sideways"

    local_abstain = noise.abstain and horizon == "5m"
    suggested_action: SuggestedAction = "wait"
    if local_abstain:
        suggested_action = "abstain"
    elif bias == "bearish" and horizon != "5m":
        suggested_action = "exit"
    elif bias == "bullish" and confidence >= (66 if horizon == "5m" else 62):
        suggested_action = "enter"
    elif bias == "bullish" and confidence >= 52:
        suggested_action = "hold"
    elif noise.confirmation_needed and bias != "bearish":
        suggested_action = "wait"

    if confidence < 45 and suggested_action in {"enter", "hold"}:
        suggested_action = "wait"
    if bias == "sideways" and suggested_action != "exit":
        suggested_action = "wait"

    explanation = ", ".join(dict.fromkeys(parts)) or "evidence is limited"
    return AIHorizonSignal(
        horizon=horizon,  # type: ignore[arg-type]
        bias=bias,
        confidence=confidence,
        suggested_action=suggested_action,
        abstain=local_abstain,
        confirmation_needed=noise.confirmation_needed and suggested_action == "wait",
        explanation=explanation[0].upper() + explanation[1:] + ".",
    )


def _horizon_return(features: AIFeatureVector, horizon: str) -> Decimal | None:
    if horizon == "5m":
        return features.return_5m
    if horizon == "15m":
        return features.return_15m
    return features.return_1h


def _score_to_confidence(score: Decimal) -> int:
    return int((abs(score) * Decimal("8")).quantize(Decimal("1")))


def _component_disagreement(features: AIFeatureVector) -> int:
    disagreement = 0
    if (
        features.technical_trend_direction == "bullish"
        and features.market_state == "risk_off"
    ) or (
        features.technical_trend_direction == "bearish"
        and features.market_state == "risk_on"
    ):
        disagreement += 1
    if (
        features.multi_timeframe_agreement == "mixed"
        or features.selected_symbol_relative_strength == "underperforming_btc"
            and features.technical_trend_direction == "bullish"
    ):
        disagreement += 1
    if features.reversal_risk in {"high", "medium"}:
        disagreement += 1
    return disagreement


def _evidence_is_thin(features: AIFeatureVector, *, horizon: str) -> bool:
    minimum_candles = {"5m": 10, "15m": 20, "1h": 60}[horizon]
    return (
        features.candle_count < minimum_candles
        or features.technical_trend_strength_score is None
        or features.structure_quality is None
    )
