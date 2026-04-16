"""Exchange models."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class SymbolFilter:
    symbol: str
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    step_size: Decimal | None = None
    tick_size: Decimal | None = None
    min_notional: Decimal | None = None
