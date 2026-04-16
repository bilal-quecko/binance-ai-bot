"""Order book models."""

from dataclasses import dataclass


@dataclass(slots=True)
class TopOfBook:
    symbol: str
    bid: float
    ask: float
