"""Default explainable weights for the unified signal fusion engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FusionWeights:
    """Relative component weights for the advisory fusion score."""

    technical_weight: Decimal = Decimal("0.30")
    pattern_weight: Decimal = Decimal("0.18")
    ai_weight: Decimal = Decimal("0.28")
    sentiment_weight: Decimal = Decimal("0.14")
    readiness_weight: Decimal = Decimal("0.10")


DEFAULT_FUSION_WEIGHTS = FusionWeights()
