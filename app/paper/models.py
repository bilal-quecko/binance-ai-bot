"""Paper-trading models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(slots=True)
class OrderRequest:
    """Typed paper-execution order request."""

    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    market_price: Decimal
    timestamp: datetime
    quote_asset: str = "USDT"
    mode: Literal["paper", "live"] = "paper"


@dataclass(slots=True)
class Position:
    """In-memory paper position state."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    quote_asset: str = "USDT"
    realized_pnl: Decimal = Decimal("0")


@dataclass(slots=True)
class FillResult:
    """Typed result for a paper execution attempt."""

    order_id: str
    status: Literal["executed", "rejected"]
    symbol: str
    side: Literal["BUY", "SELL"]
    requested_quantity: Decimal
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    quote_balance: Decimal
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    position: Position | None = None
