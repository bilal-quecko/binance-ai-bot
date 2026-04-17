"""Storage record models."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True)
class TradeRecord:
    """Persisted trade record."""

    order_id: str
    symbol: str
    side: str
    requested_quantity: Decimal
    approved_quantity: Decimal
    filled_quantity: Decimal
    status: str
    risk_decision: str
    reason_codes: tuple[str, ...]
    fill_price: Decimal
    realized_pnl: Decimal
    quote_balance: Decimal
    event_time: datetime


@dataclass(slots=True)
class FillRecord:
    """Persisted fill record."""

    order_id: str
    symbol: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    quote_balance: Decimal
    event_time: datetime


@dataclass(slots=True)
class PositionSnapshotRecord:
    """Persisted position snapshot."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    realized_pnl: Decimal
    quote_asset: str
    snapshot_time: datetime


@dataclass(slots=True)
class PnlSnapshotRecord:
    """Persisted PnL snapshot."""

    snapshot_time: datetime
    equity: Decimal
    total_pnl: Decimal
    realized_pnl: Decimal
    cash_balance: Decimal


@dataclass(slots=True)
class EquityHistoryPoint:
    """Persisted equity history point."""

    snapshot_time: datetime
    equity: Decimal


@dataclass(slots=True)
class PnlHistoryPoint:
    """Persisted PnL history point."""

    snapshot_time: datetime
    total_pnl: Decimal
    realized_pnl: Decimal


@dataclass(slots=True)
class DailyPnlRecord:
    """Derived daily PnL point from persisted snapshots."""

    day: date
    total_pnl: Decimal
    realized_pnl: Decimal


@dataclass(slots=True)
class DrawdownPoint:
    """Derived drawdown point from persisted equity snapshots."""

    snapshot_time: datetime
    equity: Decimal
    peak_equity: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal


@dataclass(slots=True)
class DrawdownSummary:
    """Derived drawdown summary and time series."""

    current_drawdown: Decimal
    current_drawdown_pct: Decimal
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    points: list[DrawdownPoint]


@dataclass(slots=True)
class RunnerEventRecord:
    """Persisted runner event."""

    event_type: str
    symbol: str
    message: str
    payload_json: str
    event_time: datetime
