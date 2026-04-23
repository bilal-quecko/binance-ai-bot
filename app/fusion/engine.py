"""Unified advisory fusion engine."""

from __future__ import annotations

from app.fusion.models import FusionInputs, FusionSignalSnapshot, empty_fusion_snapshot
from app.fusion.scoring import build_fusion_signal
from app.fusion.weights import DEFAULT_FUSION_WEIGHTS, FusionWeights


class UnifiedSignalFusionEngine:
    """Combine analysis layers into one advisory trading action."""

    def __init__(self, weights: FusionWeights = DEFAULT_FUSION_WEIGHTS) -> None:
        self._weights = weights

    def build_signal(self, inputs: FusionInputs) -> FusionSignalSnapshot:
        """Return a fused symbol-scoped advisory signal."""

        if inputs.trade_readiness is None and inputs.ai_signal is None and inputs.technical_analysis is None:
            return empty_fusion_snapshot(
                symbol=inputs.symbol,
                status_message=f"Fusion signal for {inputs.symbol} still needs runtime, analysis, and readiness context.",
            )
        if inputs.technical_analysis is None or inputs.technical_analysis.data_state != "ready":
            return empty_fusion_snapshot(
                symbol=inputs.symbol,
                status_message=f"Fusion signal for {inputs.symbol} is waiting for technical analysis to become ready.",
            )
        if inputs.ai_signal is None:
            return empty_fusion_snapshot(
                symbol=inputs.symbol,
                status_message=f"Fusion signal for {inputs.symbol} is waiting for AI advisory context.",
            )
        if inputs.trade_readiness is None:
            return empty_fusion_snapshot(
                symbol=inputs.symbol,
                status_message=f"Fusion signal for {inputs.symbol} is waiting for deterministic trade readiness.",
            )
        snapshot = build_fusion_signal(inputs=inputs, weights=self._weights)
        if inputs.pattern_analysis is None or inputs.pattern_analysis.data_state != "ready":
            snapshot.data_state = "incomplete"
            snapshot.status_message = (
                f"Fusion signal for {inputs.symbol} is usable, but multi-horizon pattern context is still incomplete."
            )
        elif inputs.symbol_sentiment is None or inputs.symbol_sentiment.data_state != "ready":
            snapshot.data_state = "incomplete"
            snapshot.status_message = (
                f"Fusion signal for {inputs.symbol} is usable, but symbol sentiment context is still incomplete."
            )
        return snapshot
