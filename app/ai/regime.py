"""Market-regime classification for advisory AI scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.ai.models import AIFeatureVector, AIRegime


@dataclass(slots=True)
class RegimeClassification:
    """Deterministic current-regime view for AI advisory logic."""

    regime: AIRegime
    weakening_factors: tuple[str, ...] = field(default_factory=tuple)


def classify_ai_regime(features: AIFeatureVector) -> RegimeClassification:
    """Classify the current market regime from technical and market context."""

    weakening: list[str] = []
    direction_flip_rate = features.direction_flip_rate or Decimal("0")
    momentum_persistence = features.momentum_persistence or Decimal("0")
    trend_strength_score = features.technical_trend_strength_score or 0

    if features.volatility_regime == "high" and direction_flip_rate >= Decimal("0.50"):
        weakening.append("volatility_is_unstable")
        return RegimeClassification(
            regime="high_volatility_unstable",
            weakening_factors=tuple(weakening),
        )

    if features.reversal_risk == "high":
        weakening.append("reversal_risk_is_elevated")
        return RegimeClassification(
            regime="reversal_risk",
            weakening_factors=tuple(weakening),
        )

    if (
        features.reversal_risk == "medium"
        and features.technical_trend_direction in {"bullish", "bearish"}
        and momentum_persistence < Decimal("0.50")
    ):
        weakening.append("reversal_risk_is_elevated")
        return RegimeClassification(
            regime="reversal_risk",
            weakening_factors=tuple(weakening),
        )

    if (
        features.technical_trend_direction in {"bullish", "bearish"}
        and trend_strength_score >= 60
        and momentum_persistence >= Decimal("0.60")
        and direction_flip_rate <= Decimal("0.25")
    ):
        return RegimeClassification(regime="trending")

    if (
        features.breakout_readiness in {"high", "medium"}
        and features.breakout_bias not in {None, "none"}
        and trend_strength_score >= 45
    ):
        if features.multi_timeframe_agreement == "mixed":
            weakening.append("multi_timeframe_alignment_is_mixed")
        return RegimeClassification(
            regime="breakout_building",
            weakening_factors=tuple(weakening),
        )

    if direction_flip_rate >= Decimal("0.45") or (features.structure_quality or Decimal("0")) < Decimal("0.38"):
        weakening.append("direction_flips_frequently")
        return RegimeClassification(
            regime="choppy",
            weakening_factors=tuple(weakening),
        )

    if (
        features.breakout_readiness in {"low", "unknown", None}
        and trend_strength_score < 45
    ):
        return RegimeClassification(regime="ranging")

    return RegimeClassification(regime="insufficient_data")
