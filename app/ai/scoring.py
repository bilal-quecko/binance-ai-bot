"""Deterministic advisory AI-style scoring with regime awareness."""

from __future__ import annotations

from app.ai.horizon_scoring import score_horizons
from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.ai.noise_filters import assess_noise
from app.ai.regime import classify_ai_regime


def score_ai_signal(features: AIFeatureVector) -> AISignalSnapshot:
    """Score advisory market bias and action from a richer deterministic feature vector."""

    regime = classify_ai_regime(features)
    noise = assess_noise(features, regime=regime.regime)
    horizon_signals = score_horizons(
        features,
        regime=regime.regime,
        noise=noise,
    )

    preferred = _pick_preferred_horizon(horizon_signals)
    aligned_bias = _aligned_bias(horizon_signals)
    selected_signal = preferred or horizon_signals[-1]

    bias = aligned_bias or selected_signal.bias
    confidence = selected_signal.confidence
    suggested_action = selected_signal.suggested_action
    abstain = noise.abstain or all(signal.abstain or signal.suggested_action == "abstain" for signal in horizon_signals)
    confirmation_needed = regime.regime == "breakout_building" or any(
        signal.confirmation_needed for signal in horizon_signals
    )

    if abstain:
        suggested_action = "abstain"
        bias = "sideways"
        confidence = min(confidence, 35)
    elif suggested_action == "enter" and confirmation_needed:
        suggested_action = "wait"

    entry_signal = suggested_action == "enter"
    exit_signal = any(signal.suggested_action == "exit" for signal in horizon_signals) or (
        regime.regime == "reversal_risk" and bias == "bearish"
    )
    low_confidence = noise.low_confidence or confidence < 50

    weakening_factors = tuple(
        dict.fromkeys((*regime.weakening_factors, *noise.weakening_factors))
    )
    explanation = _build_explanation(
        regime=regime.regime,
        preferred_horizon=preferred.horizon if preferred is not None else None,
        suggested_action=suggested_action,
        abstain=abstain,
        confirmation_needed=confirmation_needed,
        selected_signal=selected_signal,
        weakening_factors=weakening_factors,
    )

    return AISignalSnapshot(
        symbol=features.symbol,
        bias=bias,
        confidence=confidence,
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        suggested_action=suggested_action,
        explanation=explanation,
        feature_vector=features,
        regime=regime.regime,
        noise_level=noise.noise_level,
        abstain=abstain,
        low_confidence=low_confidence,
        confirmation_needed=confirmation_needed,
        preferred_horizon=preferred.horizon if preferred is not None else None,
        weakening_factors=weakening_factors,
        horizon_signals=horizon_signals,
    )


def _pick_preferred_horizon(horizon_signals):
    candidates = [
        signal
        for signal in horizon_signals
        if not signal.abstain and signal.suggested_action != "abstain"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda signal: (signal.confidence, signal.horizon == "15m", signal.horizon == "1h"))


def _aligned_bias(horizon_signals):
    directional = [signal.bias for signal in horizon_signals if signal.bias != "sideways" and not signal.abstain]
    if not directional:
        return None
    if len(set(directional)) == 1:
        return directional[0]
    return None


def _build_explanation(
    *,
    regime: str,
    preferred_horizon: str | None,
    suggested_action: str,
    abstain: bool,
    confirmation_needed: bool,
    selected_signal,
    weakening_factors: tuple[str, ...],
) -> str:
    """Build a concise advisory explanation with abstention clarity."""

    parts = [
        f"Regime is {regime.replace('_', ' ')}.",
    ]
    if preferred_horizon is not None:
        parts.append(
            f"The strongest current read comes from the {preferred_horizon} horizon with a {selected_signal.bias} bias."
        )
    if abstain:
        parts.append("AI is abstaining because short-timeframe conditions look too noisy.")
    elif confirmation_needed:
        parts.append("AI wants confirmation before treating the setup as actionable.")
    else:
        parts.append(f"Recommended action is {suggested_action}.")
    if weakening_factors:
        parts.append(
            "Confidence is being reduced by "
            + ", ".join(factor.replace("_", " ") for factor in weakening_factors[:3])
            + "."
        )
    else:
        parts.append(selected_signal.explanation)
    return " ".join(parts)
