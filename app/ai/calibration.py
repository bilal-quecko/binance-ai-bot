"""Confidence shaping for advisory AI outputs."""

from __future__ import annotations

from app.ai.models import AIRegime, HorizonName, NoiseLevel


def shape_confidence(
    *,
    raw_confidence: int,
    horizon: HorizonName,
    regime: AIRegime,
    noise_level: NoiseLevel,
    component_disagreement: int,
    evidence_thin: bool,
    low_confidence: bool,
    confirmation_needed: bool,
) -> int:
    """Shape raw confidence into a more conservative 0..100 advisory score."""

    confidence = raw_confidence

    if regime == "choppy":
        confidence -= 16
    elif regime == "high_volatility_unstable":
        confidence -= 22
    elif regime == "ranging":
        confidence -= 10
    elif regime == "reversal_risk":
        confidence -= 12
    elif regime == "breakout_building":
        confidence -= 5 if horizon == "5m" else 0

    if noise_level == "moderate":
        confidence -= 8
    elif noise_level == "high":
        confidence -= 16
    elif noise_level == "extreme":
        confidence -= 24

    confidence -= component_disagreement * 5

    if evidence_thin:
        confidence -= 8
    if low_confidence:
        confidence -= 6
    if confirmation_needed:
        confidence -= 7

    if horizon == "5m" and noise_level in {"high", "extreme"}:
        confidence = min(confidence, 42)
    elif horizon == "5m" and confirmation_needed:
        confidence = min(confidence, 55)
    elif horizon == "15m" and component_disagreement >= 2:
        confidence = min(confidence, 63)

    return max(0, min(100, confidence))
