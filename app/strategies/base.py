"""Strategy base types."""

from typing import Protocol

from app.features.models import FeatureSnapshot
from app.strategies.models import StrategySignal


class Strategy(Protocol):
    """Typed strategy interface for deterministic signals."""

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal:
        """Return a deterministic strategy signal for the supplied feature snapshot."""

        ...
