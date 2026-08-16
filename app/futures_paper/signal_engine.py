"""Deterministic paper Futures LONG/SHORT signal engine."""

from __future__ import annotations

from decimal import Decimal

from app.futures_paper.models import FuturesSignal, FuturesSignalInput


class FuturesSignalEngine:
    """Build paper Futures signals without AI execution authority."""

    def __init__(self, *, min_edge_buffer_pct: Decimal = Decimal("0.05")) -> None:
        self.min_edge_buffer_pct = min_edge_buffer_pct

    def evaluate(self, signal_input: FuturesSignalInput) -> FuturesSignal:
        """Return a deterministic Futures signal."""

        if signal_input.technical_bias == "insufficient" or signal_input.regime == "insufficient_data":
            return self._signal(signal_input.symbol, "WAIT", 20, "medium", ("INSUFFICIENT_HISTORY",))
        if not signal_input.volatility_safe:
            return self._signal(signal_input.symbol, "AVOID", 18, "high", ("VOLATILITY_UNSAFE",), "Volatility is unsafe.")
        if not signal_input.spread_safe:
            return self._signal(signal_input.symbol, "AVOID", 18, "high", ("SPREAD_UNSAFE",), "Spread or liquidity is unsafe.")
        if (
            signal_input.expected_edge_pct is not None
            and signal_input.expected_edge_pct <= signal_input.estimated_cost_pct + self.min_edge_buffer_pct
        ):
            return self._signal(signal_input.symbol, "AVOID", 24, "medium", ("EDGE_BELOW_COSTS",), "Edge is below costs.")
        if (
            signal_input.liquidation_distance_pct is not None
            and signal_input.liquidation_distance_pct < Decimal("12")
        ):
            return self._signal(signal_input.symbol, "AVOID", 20, "high", ("LIQUIDATION_RISK_HIGH",), "Liquidation distance is too tight.")
        if signal_input.current_position_side == "LONG" and signal_input.long_invalidation:
            return self._signal(signal_input.symbol, "CLOSE_LONG", 72, "medium", ("CLOSE_SIGNAL_ACTIVE",))
        if signal_input.current_position_side == "SHORT" and signal_input.short_invalidation:
            return self._signal(signal_input.symbol, "CLOSE_SHORT", 72, "medium", ("CLOSE_SIGNAL_ACTIVE",))

        bullish_votes = self._votes(signal_input, "bullish")
        bearish_votes = self._votes(signal_input, "bearish")
        validation_ok = signal_input.validation_score is None or signal_input.validation_score >= Decimal("0.45")
        if not validation_ok:
            return self._signal(signal_input.symbol, "WAIT", 40, "medium", ("VALIDATION_INSUFFICIENT",))
        if signal_input.regime not in {"bullish", "bearish", "range", "unknown"}:
            return self._signal(signal_input.symbol, "AVOID", 28, "high", ("REGIME_NOT_SUPPORTED",))
        if bullish_votes >= 3 and bullish_votes > bearish_votes:
            return self._signal(signal_input.symbol, "LONG", min(95, 52 + bullish_votes * 10), "medium", ("FUTURES_LONG_ALIGNMENT",))
        if bearish_votes >= 3 and bearish_votes > bullish_votes:
            return self._signal(signal_input.symbol, "SHORT", min(95, 52 + bearish_votes * 10), "medium", ("FUTURES_SHORT_ALIGNMENT",))
        return self._signal(signal_input.symbol, "WAIT", 42, "medium", ("MIXED_SIGNAL",))

    @staticmethod
    def _votes(signal_input: FuturesSignalInput, side: str) -> int:
        values = (
            signal_input.technical_bias,
            signal_input.regime,
            signal_input.market_sentiment,
            signal_input.symbol_sentiment,
            signal_input.pattern_bias,
        )
        return sum(1 for value in values if value == side)

    @staticmethod
    def _signal(
        symbol: str,
        side: str,
        confidence: int,
        risk_grade: str,
        reason_codes: tuple[str, ...],
        blocker_reason: str | None = None,
    ) -> FuturesSignal:
        return FuturesSignal(
            symbol=symbol.upper(),
            side=side,  # type: ignore[arg-type]
            confidence=confidence,
            risk_grade=risk_grade,  # type: ignore[arg-type]
            reason_codes=reason_codes,
            blocker_reason=blocker_reason,
        )
