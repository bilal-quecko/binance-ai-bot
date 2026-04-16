"""Strategy base types."""

from typing import Protocol

from app.features.models import FeatureSnapshot
from app.strategies.models import StrategySignal


class Strategy(Protocol):
    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal | None:
        ...
