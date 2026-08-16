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
class FuturesPaperEventRecord:
    """Persisted paper Futures event."""

    event_type: str
    symbol: str
    payload_json: str
    event_time: datetime


@dataclass(slots=True)
class FuturesPaperFillRecord:
    """Persisted paper Futures fill."""

    order_id: str
    status: str
    symbol: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    reason_codes: tuple[str, ...]
    event_time: datetime


@dataclass(slots=True)
class FuturesPaperPositionRecord:
    """Persisted current paper Futures position."""

    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    leverage: int
    margin_mode: str
    margin_used: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price_estimate: Decimal
    opened_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class FuturesPaperPnlSnapshotRecord:
    """Persisted paper Futures PnL snapshot."""

    symbol: str
    snapshot_time: datetime
    unrealized_pnl: Decimal
    realized_pnl: Decimal


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
class ScannerValidationSnapshotRecord:
    """Persisted futures-paper scanner signal snapshot for outcome validation."""

    id: int | None
    scan_id: str
    symbol: str
    direction: str
    price_at_scan: Decimal | None
    opportunity_score: int
    confidence: int
    horizon: str
    risk_grade: str
    trend_score: int
    momentum_score: int
    volatility_quality_score: int
    liquidity_score: int
    risk_score: int
    direction_score: int
    validation_score: int | None
    evidence_strength: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    timestamp: datetime
    rank_position: int
    candidate_group: str
    regime_label: str | None = None
    data_source: str | None = None


@dataclass(slots=True)
class ScannerValidationOutcomeRecord:
    """Persisted forward outcome for one scanner-validation horizon."""

    id: int | None
    snapshot_id: int
    horizon: str
    future_price: Decimal | None
    gross_return_pct: Decimal | None
    estimated_fee_pct: Decimal
    estimated_slippage_pct: Decimal
    net_return_pct: Decimal | None
    direction_correct: bool | None
    max_favorable_move_pct: Decimal | None
    max_adverse_move_pct: Decimal | None
    take_profit_hit: bool
    stop_loss_hit: bool
    first_exit: str | None
    outcome_state: str
    evaluated_at: datetime


@dataclass(slots=True)
class SignalOutcomeSnapshotRecord:
    """Persisted generated signal snapshot for post-signal outcome tracking."""

    id: str
    symbol: str
    timestamp: datetime
    source: str
    signal_type: str
    confidence: int
    entry_price: Decimal | None
    liquidity_bias: str | None
    sweep_risk: str | None
    nearest_liquidity_above: Decimal | None
    nearest_liquidity_below: Decimal | None
    funding_rate: Decimal | None
    open_interest: Decimal | None
    notes: str
    heatmap_liquidity_above: Decimal | None = None
    heatmap_liquidity_below: Decimal | None = None
    heatmap_intensity_score: int | None = None
    heatmap_bias: str | None = None
    base_signal_type: str | None = None
    heatmap_signal_type: str | None = None
    base_confidence: int | None = None
    heatmap_confidence: int | None = None
    heatmap_alignment: str | None = None
    heatmap_explanation: str | None = None
    heatmap_provider: str | None = None
    heatmap_data_quality: str | None = None
    heatmap_is_real_data: bool | None = None
    heatmap_provider_status: str | None = None
    liquidation_pressure: str | None = None
    liquidation_imbalance: Decimal | None = None


@dataclass(slots=True)
class SignalOutcomeRecord:
    """Persisted fixed-horizon outcome for one generated signal."""

    id: int | None
    signal_id: str
    horizon: str
    future_price: Decimal | None
    price_change_percent: Decimal | None
    max_upside_percent: Decimal | None
    max_downside_percent: Decimal | None
    did_price_hit_tp: bool
    did_price_hit_sl: bool
    direction_correct: bool | None
    volatility_range: Decimal | None
    first_hit: str | None
    time_to_hit_seconds: int | None
    sweep_direction_actual: str
    sweep_prediction_correct: bool | None
    outcome_state: str
    evaluated_at: datetime
    base_signal_correct: bool | None = None
    heatmap_signal_correct: bool | None = None
    did_heatmap_improve_result: bool | None = None
    did_heatmap_reduce_loss: bool | None = None
    predicted_sweep_direction: str = "none"
    actual_sweep_direction: str = "none"


@dataclass(slots=True)
class SignalTimingBaselineRecord:
    """Persisted timing-quality baseline for one actionable signal horizon."""

    id: int | None
    signal_id: str
    horizon: str
    symbol: str
    source: str
    direction: str
    signal_time: datetime
    setup_start_time: datetime | None
    setup_start_price: Decimal | None
    activation_price: Decimal | None
    recent_swing_low: Decimal | None
    recent_swing_high: Decimal | None
    horizon_end_price: Decimal | None
    max_favorable_price: Decimal | None
    max_adverse_price: Decimal | None
    move_before_signal_pct: Decimal | None
    move_after_signal_pct: Decimal | None
    max_favorable_excursion_pct: Decimal | None
    max_adverse_excursion_pct: Decimal | None
    full_move_pct: Decimal | None
    move_already_consumed_pct: Decimal | None
    move_capture_ratio_pct: Decimal | None
    entry_efficiency_pct: Decimal | None
    pre_move_lead_time_seconds: int | None
    signal_to_entry_latency_seconds: int | None
    time_to_target_seconds: int | None
    time_to_stop_seconds: int | None
    expiry_seconds: int
    net_return_after_costs_pct: Decimal | None
    estimated_round_trip_cost_pct: Decimal
    realized_volatility_pct: Decimal | None
    regime_label: str | None
    liquidity_context: str | None
    classification: str
    classification_reasons: tuple[str, ...]
    outcome_state: str
    evaluated_at: datetime


@dataclass(slots=True)
class ContinuousIntelligenceStateRecord:
    """Persisted checkpoint for the backend-owned continuous market service."""

    enabled: bool
    status: str
    cycle_id: str | None
    started_at: datetime | None
    last_cycle_started_at: datetime | None
    last_cycle_completed_at: datetime | None
    last_full_universe_pass_at: datetime | None
    last_universe_refresh_at: datetime | None
    last_websocket_event_at: datetime | None
    next_cycle_at: datetime | None
    last_error: str | None
    universe_source: str
    total_symbols: int
    fast_screened_symbols: int
    deep_analyzed_symbols: int
    deep_queue_depth: int
    successful_cycles: int
    failed_cycles: int
    consecutive_failures: int
    config_json: str
    updated_at: datetime


@dataclass(slots=True)
class ContinuousIntelligenceCandidateRecord:
    """Latest persisted continuous screening state for one market symbol."""

    market: str
    symbol: str
    stage: str
    fast_score: int
    deep_score: int | None
    direction_hint: str
    current_price: Decimal | None
    triggers: tuple[str, ...]
    metrics_json: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    screened_at: datetime
    deep_analyzed_at: datetime | None
    data_source: str


@dataclass(slots=True)
class ContinuousIntelligenceCycleRecord:
    """Persisted summary of one continuous market-intelligence cycle."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    universe_source: str
    total_symbols: int
    fast_screened_symbols: int
    deep_analyzed_symbols: int
    candidate_count: int
    failed_symbols: tuple[str, ...]
    error_message: str | None
    duration_ms: int | None


@dataclass(slots=True)
class ScannerRunRecord:
    """Persisted scanner run metadata for replayable market scans."""

    id: str
    generated_at: datetime
    quote_asset: str
    horizon: str
    max_symbols: int
    min_opportunity_score: int
    scan_state: str
    scanned_count: int
    failed_symbols_json: str
    warnings_json: str
    result_json: str | None = None
    candidate_count: int = 0


@dataclass(slots=True)
class ScannerCandidateRecord:
    """Persisted scanner candidate from one scanner run."""

    id: str
    scanner_run_id: str
    symbol: str
    direction: str
    opportunity_score: int
    confidence: int
    evidence_strength: str
    current_price: Decimal | None
    entry_zone: str | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    risk_grade: str
    regime: str | None
    reason: str
    warnings_json: str
    timestamp: datetime


@dataclass(slots=True)
class ScannerCandidatePriceRecord:
    """Persisted price observation tied to a scanner candidate."""

    id: int | None
    scanner_candidate_id: str
    symbol: str
    price: Decimal | None
    price_type: str
    source: str
    recorded_at: datetime


@dataclass(slots=True)
class SymbolAnalysisCacheRecord:
    """Persisted symbol analysis cache entry."""

    symbol: str
    analysis_type: str
    horizon: str
    payload_json: str
    generated_at: datetime
    expires_at: datetime
    data_state: str


@dataclass(slots=True)
class SymbolBackfillJobRecord:
    """Persisted symbol backfill job state."""

    id: str
    symbol: str
    interval: str
    lookback_days: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    candles_inserted: int


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
