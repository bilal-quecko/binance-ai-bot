"""Deterministic trend-following strategy."""

from decimal import Decimal

from app.features.models import FeatureSnapshot
from app.strategies.models import StrategySignal, TrendFollowingConfig


class TrendFollowingStrategy:
    """Buy only when trend and market-quality filters agree."""

    def __init__(self, config: TrendFollowingConfig | None = None) -> None:
        self.config = config or TrendFollowingConfig()

    def _hold(self, symbol: str, *reason_codes: str) -> StrategySignal:
        """Return a typed HOLD signal with deterministic reason codes."""

        return StrategySignal(
            symbol=symbol,
            side="HOLD",
            confidence=self.config.hold_confidence,
            reason_codes=tuple(reason_codes),
        )

    def _atr_ratio(self, snapshot: FeatureSnapshot) -> Decimal | None:
        """Return ATR as a fraction of the current mid price when available."""

        if snapshot.atr is None or snapshot.mid_price in {None, Decimal("0")}:
            return None
        return snapshot.atr / snapshot.mid_price

    def _is_spread_healthy(self, snapshot: FeatureSnapshot) -> bool:
        """Return whether spread and imbalance pass deterministic sanity checks."""

        if snapshot.bid_ask_spread is None or snapshot.mid_price in {None, Decimal("0")}:
            return False

        spread_ratio = snapshot.bid_ask_spread / snapshot.mid_price
        if spread_ratio > self.config.max_spread_ratio:
            return False

        if (
            snapshot.order_book_imbalance is not None
            and snapshot.order_book_imbalance < self.config.min_order_book_imbalance
        ):
            return False

        return True

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal:
        """Evaluate a feature snapshot and return a deterministic signal."""

        if snapshot.ema_fast is None or snapshot.ema_slow is None:
            return self._hold(snapshot.symbol, "MISSING_EMA")
        if snapshot.regime != "bullish":
            return self._hold(snapshot.symbol, "REGIME_NOT_TREND")

        atr_ratio = self._atr_ratio(snapshot)
        if atr_ratio is None:
            return self._hold(snapshot.symbol, "MISSING_ATR_CONTEXT")
        if atr_ratio < self.config.min_atr_ratio:
            return self._hold(snapshot.symbol, "VOL_TOO_LOW")
        if atr_ratio > self.config.max_atr_ratio:
            return self._hold(snapshot.symbol, "VOL_TOO_HIGH")
        if not self._is_spread_healthy(snapshot):
            return self._hold(snapshot.symbol, "MICROSTRUCTURE_UNHEALTHY")
        if snapshot.ema_fast <= snapshot.ema_slow:
            return self._hold(snapshot.symbol, "EMA_NOT_BULLISH")

        return StrategySignal(
            symbol=snapshot.symbol,
            side="BUY",
            confidence=self.config.buy_confidence,
            reason_codes=("EMA_BULLISH", "REGIME_TREND", "RISK_FILTERS_PASS"),
        )
