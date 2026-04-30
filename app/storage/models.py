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
    execution_source: str = "auto"
    trading_profile: str = "balanced"
    session_id: str | None = None
    tuning_version_id: str | None = None


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
    execution_source: str = "auto"
    trading_profile: str = "balanced"
    session_id: str | None = None
    tuning_version_id: str | None = None


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
    regime: str | None = None
    noise_level: str | None = None
    abstain: bool = False
    low_confidence: bool = False
    confirmation_needed: bool = False
    preferred_horizon: str | None = None
    momentum_persistence: Decimal | None = None
    direction_flip_rate: Decimal | None = None
    structure_quality: Decimal | None = None
    recent_false_positive_rate_5m: Decimal | None = None
    horizons: dict[str, dict[str, object]] | None = None
    weakening_factors: tuple[str, ...] = ()


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
class SignalValidationSnapshotRecord:
    """Persisted final signal and trading-assistant decision for validation."""

    id: int | None
    symbol: str
    timestamp: datetime
    price: Decimal
    final_action: str
    fusion_final_signal: str
    confidence: int
    expected_edge_pct: Decimal | None
    estimated_cost_pct: Decimal | None
    risk_grade: str
    preferred_horizon: str
    technical_score: Decimal | None
    technical_context_json: str
    sentiment_score: Decimal | None
    sentiment_context_json: str
    pattern_score: Decimal | None
    pattern_context_json: str
    ai_context_json: str
    top_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    invalidation_hint: str | None
    trade_opened: bool
    signal_ignored_or_blocked: bool
    blocker_reasons: tuple[str, ...]
    regime_label: str | None = None


@dataclass(slots=True)
class HistoricalCandleRecord:
    """Persisted full OHLCV candle history record."""

    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    source: str
    created_at: datetime


@dataclass(slots=True)
class RuntimeSessionRecord:
    """Persisted backend-owned runtime session state."""

    state: str
    mode: str
    trading_profile: str
    symbol: str | None
    session_id: str | None
    started_at: datetime | None
    last_event_time: datetime | None
    last_error: str | None
    tuning_version_id: str | None = None
    baseline_tuning_version_id: str | None = None


@dataclass(slots=True)
class PaperBrokerStateRecord:
    """Persisted paper broker recovery state."""

    balances: dict[str, Decimal]
    positions: list[PositionSnapshotRecord]
    realized_pnl: Decimal
    snapshot_time: datetime


@dataclass(slots=True)
class ProfileTuningSetRecord:
    """Persisted paper-profile tuning configuration."""

    version_id: str
    symbol: str | None
    profile: str
    status: str
    config_json: str
    baseline_config_json: str
    created_at: datetime
    applied_at: datetime | None
    baseline_version_id: str | None
    reason: str


@dataclass(slots=True)
class PaperSessionRunRecord:
    """Persisted paper session metadata for before/after comparison."""

    session_id: str
    symbol: str
    trading_profile: str
    tuning_version_id: str | None
    baseline_tuning_version_id: str | None
    started_at: datetime
    ended_at: datetime | None
