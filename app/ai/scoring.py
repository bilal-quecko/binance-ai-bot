"""Deterministic advisory AI-style scoring."""

from __future__ import annotations

from decimal import Decimal

from app.ai.models import AIFeatureVector, AISignalSnapshot


def _clamp_confidence(value: int) -> int:
    """Clamp confidence to a user-facing 0..100 range."""

    return max(0, min(100, value))


def score_ai_signal(features: AIFeatureVector) -> AISignalSnapshot:
    """Score advisory market bias and action from a deterministic feature vector."""

    bias_score = Decimal("0")
    confidence = 50
    explanation_parts: list[str] = []

    if features.ema_fast is not None and features.ema_slow is not None:
        if features.ema_fast > features.ema_slow:
            bias_score += Decimal("2")
            confidence += 10
            explanation_parts.append("fast EMA is above slow EMA")
        elif features.ema_fast < features.ema_slow:
            bias_score -= Decimal("2")
            confidence += 10
            explanation_parts.append("fast EMA is below slow EMA")
        else:
            explanation_parts.append("EMAs are flat")

    if features.momentum is not None:
        if features.momentum > Decimal("0.004"):
            bias_score += Decimal("1.5")
            confidence += 8
            explanation_parts.append("recent momentum is improving")
        elif features.momentum < Decimal("-0.004"):
            bias_score -= Decimal("1.5")
            confidence += 8
            explanation_parts.append("recent momentum is weakening")

    if features.rsi is not None:
        if features.rsi >= Decimal("58"):
            bias_score += Decimal("1")
            confidence += 6
            explanation_parts.append("RSI is leaning bullish")
        elif features.rsi <= Decimal("42"):
            bias_score -= Decimal("1")
            confidence += 6
            explanation_parts.append("RSI is leaning bearish")
        else:
            explanation_parts.append("RSI is neutral")

    if features.volume_spike_ratio is not None:
        if features.volume_spike_ratio >= Decimal("1.4"):
            confidence += 7
            explanation_parts.append("volume is above its recent baseline")
        elif features.volume_spike_ratio < Decimal("0.8"):
            confidence -= 5
            explanation_parts.append("volume is light")

    if features.volatility_pct is not None:
        if Decimal("0.001") <= features.volatility_pct <= Decimal("0.03"):
            confidence += 6
            explanation_parts.append("volatility is in a workable range")
        elif features.volatility_pct > Decimal("0.05"):
            confidence -= 8
            explanation_parts.append("volatility is elevated")
        else:
            confidence -= 3
            explanation_parts.append("volatility is muted")

    if features.microstructure_healthy:
        confidence += 5
        explanation_parts.append("spread and top-of-book look healthy")
    elif features.spread_ratio is not None:
        confidence -= 6
        explanation_parts.append("spread or top-of-book conditions are less favorable")

    if features.wick_body_ratio is not None and features.wick_body_ratio > Decimal("3"):
        confidence -= 4
        explanation_parts.append("the latest candle has high wick noise")

    if bias_score >= Decimal("2.5"):
        bias = "bullish"
    elif bias_score <= Decimal("-2.5"):
        bias = "bearish"
    else:
        bias = "sideways"

    entry_signal = (
        bias == "bullish"
        and features.momentum is not None
        and features.momentum > Decimal("0")
        and features.rsi is not None
        and features.rsi < Decimal("72")
        and (features.volatility_pct is None or features.volatility_pct <= Decimal("0.035"))
        and (features.spread_ratio is None or features.spread_ratio <= Decimal("0.0025"))
    )
    exit_signal = (
        bias == "bearish"
        or (
            features.rsi is not None
            and features.rsi >= Decimal("74")
        )
        or (
            features.momentum is not None
            and features.momentum < Decimal("-0.003")
        )
    )

    suggested_action = "wait"
    if exit_signal:
        suggested_action = "exit"
    elif entry_signal:
        suggested_action = "enter"
    elif bias == "bullish":
        suggested_action = "hold"

    if suggested_action == "enter" and confidence < 60:
        suggested_action = "wait"
        explanation_parts.append("setup exists but confidence is still moderate")
    if bias == "sideways" and suggested_action != "exit":
        suggested_action = "wait"

    explanation = ", ".join(dict.fromkeys(explanation_parts)) or "insufficient context"

    return AISignalSnapshot(
        symbol=features.symbol,
        bias=bias,
        confidence=_clamp_confidence(confidence),
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        suggested_action=suggested_action,
        explanation=explanation[0].upper() + explanation[1:] + ".",
        feature_vector=features,
    )
