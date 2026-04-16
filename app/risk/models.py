"""Risk models."""

from dataclasses import dataclass


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str
    size_multiplier: float = 1.0
