"""Trend-following strategy placeholder."""

from app.features.models import FeatureSnapshot
from app.strategies.models import StrategySignal


class TrendFollowingStrategy:
    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal | None:
        if snapshot.ema_fast is None or snapshot.ema_slow is None:
            return None
        if snapshot.ema_fast > snapshot.ema_slow:
            return StrategySignal(symbol=snapshot.symbol, side="BUY", confidence=0.55, reason_codes=["EMA_BULL"])
        if snapshot.ema_fast < snapshot.ema_slow:
            return StrategySignal(symbol=snapshot.symbol, side="SELL", confidence=0.55, reason_codes=["EMA_BEAR"])
        return None
