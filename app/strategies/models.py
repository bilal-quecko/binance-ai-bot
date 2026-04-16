"""Strategy models."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class StrategySignal:
    symbol: str
    side: str
    confidence: float
    reason_codes: list[str] = field(default_factory=list)
