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


@dataclass(slots=True)
class AISignalFeatureSummaryRecord:
    """Compact persisted AI feature summary."""

    candle_count: int
    close_price: Decimal
    volatility_pct: Decimal | None
    momentum: Decimal | None
    volume_change_pct: Decimal | None
    volume_spike_ratio: Decimal | None
    spread_ratio: Decimal | None
    microstructure_healthy: bool


@dataclass(slots=True)
class AISignalSnapshotRecord:
    """Persisted AI advisory snapshot."""

    symbol: str
    timestamp: datetime
    bias: str
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: str
    explanation: str
    feature_summary: AISignalFeatureSummaryRecord


@dataclass(slots=True)
class MarketCandleSnapshotRecord:
    """Persisted closed-candle snapshot for later evaluation."""

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    close_price: Decimal
    event_time: datetime


@dataclass(slots=True)
class RuntimeSessionRecord:
    """Persisted backend-owned runtime session state."""

    state: str
    mode: str
    symbol: str | None
    session_id: str | None
    started_at: datetime | None
    last_event_time: datetime | None
    last_error: str | None


@dataclass(slots=True)
class PaperBrokerStateRecord:
    """Persisted paper broker recovery state."""

    balances: dict[str, Decimal]
    positions: list[PositionSnapshotRecord]
    realized_pnl: Decimal
    snapshot_time: datetime
