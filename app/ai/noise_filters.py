"""Short-timeframe noise filters for advisory AI scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.ai.models import AIFeatureVector, AIRegime, NoiseLevel


@dataclass(slots=True)
class NoiseFilterDecision:
    """Deterministic noise assessment and abstention guidance."""

    noise_level: NoiseLevel
    abstain: bool
    low_confidence: bool
    confirmation_needed: bool
    weakening_factors: tuple[str, ...] = field(default_factory=tuple)


def assess_noise(
    features: AIFeatureVector,
    *,
    regime: AIRegime,
) -> NoiseFilterDecision:
    """Assess short-timeframe noise and whether AI should abstain or wait."""

    weakening: list[str] = []
    severity = 0

    if features.spread_ratio is not None and features.spread_ratio > Decimal("0.0025"):
        severity += 2
        weakening.append("spread_is_wide")
    elif features.spread_ratio is not None and features.spread_ratio > Decimal("0.0015"):
        severity += 1
        weakening.append("spread_needs_tighter_liquidity")

    if features.volatility_regime == "high" or (
        features.volatility_pct is not None and features.volatility_pct > Decimal("0.04")
    ):
        severity += 2
        weakening.append("volatility_is_unstable")

    if features.momentum_persistence is not None and features.momentum_persistence < Decimal("0.45"):
        severity += 2
        weakening.append("momentum_is_inconsistent")
    elif features.momentum_persistence is not None and features.momentum_persistence < Decimal("0.58"):
        severity += 1
        weakening.append("momentum_needs_confirmation")

    if features.direction_flip_rate is not None and features.direction_flip_rate >= Decimal("0.45"):
        severity += 2
        weakening.append("direction_flips_frequently")
    elif features.direction_flip_rate is not None and features.direction_flip_rate >= Decimal("0.30"):
        severity += 1
        weakening.append("direction_is_not_stable")

    if features.structure_quality is not None and features.structure_quality < Decimal("0.35"):
        severity += 2
        weakening.append("structure_is_weak")
    elif features.structure_quality is not None and features.structure_quality < Decimal("0.55"):
        severity += 1
        weakening.append("structure_is_ambiguous")

    if features.breakout_readiness in {"low", "unknown", None}:
        severity += 1
        weakening.append("breakout_readiness_is_low")

    if (
        features.recent_false_positive_rate_5m is not None
        and features.recent_false_positive_rate_5m >= Decimal("35")
    ):
        severity += 2
        weakening.append("recent_5m_false_signals_are_elevated")

    if regime in {"choppy", "high_volatility_unstable"}:
        severity += 2
        weakening.append("current_regime_is_noise_prone")
    elif regime in {"ranging", "reversal_risk"}:
        severity += 1

    if severity >= 8:
        noise_level: NoiseLevel = "extreme"
    elif severity >= 5:
        noise_level = "high"
    elif severity >= 3:
        noise_level = "moderate"
    else:
        noise_level = "low"

    abstain = noise_level in {"high", "extreme"} and (
        regime in {"choppy", "high_volatility_unstable"}
        or "recent_5m_false_signals_are_elevated" in weakening
    )
    confirmation_needed = (
        not abstain
        and (
            regime == "breakout_building"
            or "momentum_needs_confirmation" in weakening
            or "structure_is_ambiguous" in weakening
        )
    )
    low_confidence = noise_level != "low" or confirmation_needed or regime in {"ranging", "reversal_risk"}

    return NoiseFilterDecision(
        noise_level=noise_level,
        abstain=abstain,
        low_confidence=low_confidence,
        confirmation_needed=confirmation_needed,
        weakening_factors=tuple(dict.fromkeys(weakening)),
    )
